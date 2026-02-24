#!/usr/bin/env node

/**
 * Fetch XHS search results with selectable sort.
 * It uses real page interactions (click sort tab) and reads window state:
 * general | time_descending | popularity_descending | comment_descending | collect_descending
 */

const fs = require("fs");
const os = require("os");
const path = require("path");

function parseArgs(argv) {
  const out = {
    keyword: "",
    browserPath: "",
    sort: "general",
    pageSize: 20,
    timeoutMs: 120000,
    cookiesFile: "",
    vendorDir: "",
    headless: true,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const k = argv[i];
    const v = argv[i + 1];
    if (k === "--keyword" && v) {
      out.keyword = v;
      i += 1;
    } else if (k === "--browser-path" && v) {
      out.browserPath = v;
      i += 1;
    } else if (k === "--sort" && v) {
      out.sort = v;
      i += 1;
    } else if (k === "--page-size" && v) {
      out.pageSize = Math.max(1, parseInt(v, 10) || 20);
      i += 1;
    } else if (k === "--timeout-ms" && v) {
      out.timeoutMs = Math.max(10000, parseInt(v, 10) || 120000);
      i += 1;
    } else if (k === "--cookies-file" && v) {
      out.cookiesFile = v;
      i += 1;
    } else if (k === "--vendor-dir" && v) {
      out.vendorDir = v;
      i += 1;
    } else if (k === "--headless" && v) {
      out.headless = !["0", "false", "no"].includes(String(v).toLowerCase());
      i += 1;
    }
  }
  return out;
}

function normalizeSort(value) {
  const raw = String(value || "general").trim().toLowerCase();
  const alias = {
    latest: "time_descending",
    newest: "time_descending",
    time: "time_descending",
    hot: "popularity_descending",
    likes: "popularity_descending",
    comments: "comment_descending",
    collects: "collect_descending",
  };
  const mapped = alias[raw] || raw;
  const allowed = new Set([
    "general",
    "time_descending",
    "popularity_descending",
    "comment_descending",
    "collect_descending",
  ]);
  return allowed.has(mapped) ? mapped : "general";
}

function safeJsonFile(filePath, fallback) {
  try {
    const text = fs.readFileSync(filePath, "utf8");
    return JSON.parse(text);
  } catch {
    return fallback;
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function sortLabels(sort) {
  const mapping = {
    time_descending: ["\u6700\u65b0", "\u6700\u65b0\u53d1\u5e03", "\u65f6\u95f4"],
    popularity_descending: ["\u6700\u70ed", "\u70ed\u95e8"],
    comment_descending: ["\u8bc4\u8bba"],
    collect_descending: ["\u6536\u85cf"],
  };
  return mapping[sort] || [];
}

async function snapshotShortLabels(page, maxCount = 120) {
  return page.evaluate((limit) => {
    const uniq = [];
    const nodes = Array.from(document.querySelectorAll("button,a,[role='button'],span,div"));
    for (const node of nodes) {
      const text = String(node.textContent || "")
        .replace(/\s+/g, " ")
        .trim();
      if (!text || text.length > 14) continue;
      if (!uniq.includes(text)) uniq.push(text);
      if (uniq.length >= limit) break;
    }
    return uniq;
  }, maxCount);
}

async function tryClickLabels(page, labels, options = {}) {
  return page.evaluate((targetLabels, opts) => {
    function normalize(text) {
      return String(text || "")
        .replace(/\s+/g, "")
        .trim();
    }
    const normalizedLabels = targetLabels.map((x) => normalize(x)).filter(Boolean);
    const exact = !!(opts && opts.exact);

    function matches(value, labels) {
      if (!value || value.length > 14) return false;
      if (exact) {
        return labels.includes(value);
      }
      return labels.some((label) => value === label || value.includes(label));
    }

    const candidates = [];
    const elements = Array.from(document.querySelectorAll("button,a,[role='button'],span,div"));
    for (const node of elements) {
      const rawText = String(node.textContent || "");
      const value = normalize(rawText);
      if (!matches(value, normalizedLabels)) continue;
      candidates.push({ node, value, rawText });
    }

    candidates.sort((a, b) => a.value.length - b.value.length);
    const seen = new Set();
    for (const item of candidates) {
      const interactive = item.node.closest("button,a,[role='button']") || item.node;
      const key = `${interactive.tagName}:${normalize(interactive.textContent || item.rawText)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      try {
        interactive.click();
        return {
          success: true,
          clicked: true,
          clicked_text: normalize(interactive.textContent || item.rawText),
        };
      } catch {
        // continue
      }
    }
    return { success: false, clicked: false, error: "label_not_found", labels: targetLabels };
  }, labels, options);
}

async function applySortByUi(page, sort, timeoutMs) {
  if (!sort || sort === "general") {
    return { success: true, clicked: false, mode: "general" };
  }

  const labels = sortLabels(sort);
  if (!labels.length) {
    return { success: false, clicked: false, error: "unsupported_sort_ui", sort };
  }

  let clickResult = await tryClickLabels(page, labels, { exact: true });
  if (!clickResult || !clickResult.success) {
    clickResult = await tryClickLabels(page, labels, { exact: false });
  }
  if (!clickResult || !clickResult.success) {
    // In current XHS UI, sort options are often under a filter panel.
    const openFilter = await tryClickLabels(page, [
      "\u7b5b\u9009",
      "\u8fc7\u6ee4",
    ], { exact: true });
    if (openFilter && openFilter.success) {
      await sleep(800);
      clickResult = await tryClickLabels(page, labels, { exact: true });
      if (!clickResult || !clickResult.success) {
        clickResult = await tryClickLabels(page, labels, { exact: false });
      }
      if (clickResult && clickResult.success) {
        clickResult.mode = "filter_panel";
      }
    }
  } else {
    clickResult.mode = "direct";
  }

  if (!clickResult || !clickResult.success) {
    const availableLabels = await snapshotShortLabels(page, 140);
    if (clickResult && typeof clickResult === "object") {
      clickResult.available_labels = availableLabels;
      return clickResult;
    }
    return {
      success: false,
      clicked: false,
      error: "sort_click_failed",
      available_labels: availableLabels,
    };
  }

  if (!clickResult.available_labels) {
    clickResult.available_labels = [];
  }

  const waitBudget = Math.max(2000, Math.min(8000, Math.floor(timeoutMs / 6)));
  try {
    await page.waitForFunction(
      (wantedSort) => {
        function unref(value) {
          if (
            value &&
            typeof value === "object" &&
            Object.prototype.hasOwnProperty.call(value, "_value")
          ) {
            return value._value;
          }
          return value;
        }
        const search = window.__INITIAL_STATE__ && window.__INITIAL_STATE__.search;
        const ctx = search ? unref(search.searchContext) || {} : {};
        const sortValue = String(ctx.sort || "general");
        return sortValue === String(wantedSort);
      },
      { timeout: waitBudget },
      sort
    );
  } catch {
    // Best effort: continue even if sort value is not exposed.
  }

  await sleep(1200);
  return clickResult;
}

async function readFeedsFromState(page) {
  return page.evaluate(() => {
    function unref(value) {
      if (
        value &&
        typeof value === "object" &&
        Object.prototype.hasOwnProperty.call(value, "_value")
      ) {
        return value._value;
      }
      if (
        value &&
        typeof value === "object" &&
        Object.prototype.hasOwnProperty.call(value, "value")
      ) {
        return value.value;
      }
      return value;
    }

    function pickFeedArray(search) {
      const directCandidates = [
        ["search.feeds", search && search.feeds],
        ["search.searchFeedsWrapper", search && search.searchFeedsWrapper],
        ["search.searchResult", search && search.searchResult],
      ];

      for (const [name, raw] of directCandidates) {
        const v = unref(raw);
        if (Array.isArray(v)) {
          return { feeds: v, source: name };
        }
        if (v && typeof v === "object") {
          const nestedKeys = ["feeds", "items", "list", "notes"];
          for (const key of nestedKeys) {
            const nested = unref(v[key]);
            if (Array.isArray(nested)) {
              return { feeds: nested, source: `${name}.${key}` };
            }
          }
        }
      }
      return { feeds: [], source: "none" };
    }

    const state = window.__INITIAL_STATE__ || {};
    const search = state.search || {};
    const picked = pickFeedArray(search);
    const context = unref(search.searchContext) || {};
    const feeds = Array.isArray(picked.feeds) ? picked.feeds : [];
    let feedsJson = "[]";
    try {
      feedsJson = JSON.stringify(feeds);
    } catch {
      feedsJson = "[]";
    }

    return {
      success: true,
      count: feeds.length,
      feeds_json: feedsJson,
      feed_source: picked.source,
      page_url: location.href,
      state_sort: String(context.sort || "general"),
      search_id: String(context.searchId || search.rootSearchId || ""),
    };
  });
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.keyword || !args.keyword.trim()) {
    console.log(JSON.stringify({ success: false, error: "missing_keyword" }));
    process.exit(2);
  }
  if (!args.browserPath) {
    console.log(JSON.stringify({ success: false, error: "missing_browser_path" }));
    process.exit(2);
  }

  const sort = normalizeSort(args.sort);
  const vendorDir = args.vendorDir || "";

  let puppeteer;
  if (vendorDir) {
    const vendorPuppeteer = path.join(vendorDir, "node_modules", "puppeteer");
    if (fs.existsSync(vendorPuppeteer)) {
      puppeteer = require(vendorPuppeteer);
    }
  }
  if (!puppeteer) {
    puppeteer = require("puppeteer");
  }

  const browser = await puppeteer.launch({
    executablePath: args.browserPath,
    headless: args.headless,
    args: ["--no-sandbox", "--disable-setuid-sandbox"],
  });

  try {
    const page = await browser.newPage();

    const cookiesPath =
      args.cookiesFile || path.join(os.homedir(), ".xhs-mcp", "cookies.json");
    if (fs.existsSync(cookiesPath)) {
      const cookies = safeJsonFile(cookiesPath, []);
      if (Array.isArray(cookies) && cookies.length > 0) {
        await page.setCookie(...cookies);
      }
    }

    const searchUrl = `https://www.xiaohongshu.com/search_result?keyword=${encodeURIComponent(
      args.keyword
    )}&source=web_explore_feed`;
    await page.goto(searchUrl, { waitUntil: "networkidle2", timeout: args.timeoutMs });
    await sleep(1600);

    const sortResult = await applySortByUi(page, sort, args.timeoutMs);
    if (!sortResult || !sortResult.success) {
      console.log(
        JSON.stringify({
          success: false,
          sort,
          error: sortResult?.error || "sort_apply_failed",
          detail: sortResult || null,
          page_url: page.url(),
        })
      );
      process.exit(1);
    }

    let stateResult = null;
    const attempts = 6;
    const attemptTrace = [];
    for (let i = 0; i < attempts; i += 1) {
      stateResult = await readFeedsFromState(page);
      attemptTrace.push({
        attempt: i + 1,
        count: stateResult && Number.isFinite(stateResult.count) ? stateResult.count : 0,
        feed_source: stateResult && stateResult.feed_source ? stateResult.feed_source : "",
        state_sort: stateResult && stateResult.state_sort ? stateResult.state_sort : "",
      });
      if (stateResult && stateResult.success && stateResult.count > 0) {
        break;
      }
      await sleep(1200);
    }

    if (!stateResult || !stateResult.success) {
      console.log(
        JSON.stringify({
          success: false,
          sort,
          error: "state_extract_failed",
          page_url: page.url(),
          detail: stateResult || null,
        })
      );
      process.exit(1);
    }

    let items = [];
    try {
      const parsed = JSON.parse(String(stateResult.feeds_json || "[]"));
      if (Array.isArray(parsed)) {
        items = parsed;
      }
    } catch {
      items = [];
    }
    const pageSize = Math.max(1, parseInt(args.pageSize, 10) || 20);
    const sliced = Array.isArray(items) ? items.slice(0, pageSize) : [];
    console.log(
      JSON.stringify({
        success: true,
        keyword: args.keyword,
        sort,
        page_url: stateResult.page_url,
        state_sort: stateResult.state_sort,
        search_id: stateResult.search_id,
        feed_source: stateResult.feed_source,
        attempt_trace: attemptTrace,
        sort_apply: sortResult,
        feeds: sliced,
        count: sliced.length,
      })
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.log(
    JSON.stringify({
      success: false,
      error: "unhandled_exception",
      message: error && error.message ? error.message : String(error),
    })
  );
  process.exit(1);
});
