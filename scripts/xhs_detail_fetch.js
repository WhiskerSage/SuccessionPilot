#!/usr/bin/env node
/* eslint-disable no-console */

const path = require("path");
const fs = require("fs");
const os = require("os");

function arg(name, fallback = "") {
  const idx = process.argv.indexOf(name);
  if (idx < 0 || idx + 1 >= process.argv.length) return fallback;
  return process.argv[idx + 1];
}

async function main() {
  const feedId = arg("--feed-id");
  const xsecToken = arg("--xsec-token");
  const browserPath = arg("--browser-path");
  const timeoutMs = Number(arg("--timeout-ms", "45000"));
  const cookiesFile = arg("--cookies-file", path.join(os.homedir(), ".xhs-mcp", "cookies.json"));

  if (!feedId || !xsecToken || !browserPath) {
    console.log(
      JSON.stringify({
        success: false,
        error: "missing_required_args",
        message: "need --feed-id --xsec-token --browser-path",
      })
    );
    process.exit(0);
  }

  let puppeteer;
  try {
    const localPath = process.env.XHS_PUPPETEER_REQUIRE ||
      "C:/Users/24264/.codex/vendor/xhs-mcp/node_modules/puppeteer";
    puppeteer = require(localPath);
  } catch (err) {
    console.log(
      JSON.stringify({
        success: false,
        error: "puppeteer_require_failed",
        message: String(err),
      })
    );
    process.exit(0);
  }

  let browser = null;
  try {
    browser = await puppeteer.launch({
      headless: true,
      executablePath: browserPath,
      timeout: timeoutMs,
      args: ["--disable-gpu", "--no-sandbox"],
    });
    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(timeoutMs);

    // Reuse xhs-mcp login cookies so detail fetch shares authenticated session.
    try {
      if (cookiesFile && fs.existsSync(cookiesFile)) {
        const raw = fs.readFileSync(cookiesFile, "utf-8");
        const cookies = JSON.parse(raw);
        if (Array.isArray(cookies) && cookies.length > 0) {
          const normalized = cookies
            .filter((c) => c && typeof c === "object" && c.name && c.value)
            .map((c) => {
              const item = {
                name: String(c.name),
                value: String(c.value),
                domain: String(c.domain || ".xiaohongshu.com"),
                path: String(c.path || "/"),
                httpOnly: Boolean(c.httpOnly),
                secure: Boolean(c.secure),
              };
              const exp = Number(c.expires);
              if (Number.isFinite(exp) && exp > 0) item.expires = exp;
              if (c.sameSite) item.sameSite = c.sameSite;
              return item;
            });
          if (normalized.length > 0) {
            await page.setCookie(...normalized);
          }
        }
      }
    } catch (_) {
      // Ignore cookie load error and continue with unauthenticated detail fetch.
    }

    const url =
      `https://www.xiaohongshu.com/explore/${feedId}?xsec_token=${encodeURIComponent(
        xsecToken
      )}&xsec_source=pc_search`;
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await new Promise((r) => setTimeout(r, 2500));

    const result = await page.evaluate(() => {
      const textOf = (sel) => {
        const el = document.querySelector(sel);
        return (el && el.textContent ? el.textContent : "").trim();
      };
      const normalize = (s) => (s || "").replace(/\s+/g, " ").trim();
      const unique = (arr) => {
        const out = [];
        for (const x of arr) {
          const v = normalize(String(x || ""));
          if (!v || out.includes(v)) continue;
          out.push(v);
        }
        return out;
      };
      const isBlockedText = (s) => {
        const t = normalize(s);
        if (!t) return false;
        return /安全限制IP存在风险|切换可靠网络环境|网络环境存在风险|访问受限|返回首页|请稍后重试|风险验证|异常请求/.test(t);
      };

      const metaDesc =
        document.querySelector('meta[name="description"]')?.getAttribute("content") || "";
      const title =
        document.querySelector('meta[property="og:title"]')?.getAttribute("content") ||
        document.title ||
        "";
      const bodyText = normalize(document.body?.innerText || "");
      const blockedByRiskPage = isBlockedText(bodyText);

      const detailCandidates = [];
      const pushDetail = (s) => {
        const t = normalize(s);
        if (!t) return;
        if (t.length < 16 || t.length > 1400) return;
        if (isBlockedText(t)) return;
        detailCandidates.push(t);
      };
      pushDetail(metaDesc);
      pushDetail(textOf('[class*="note-content"]'));
      pushDetail(textOf('[class*="desc"]'));
      pushDetail(textOf("article"));
      for (const el of Array.from(document.querySelectorAll("main p, article p, [class*='content'] p")).slice(0, 50)) {
        pushDetail(el.textContent || "");
      }

      const domComments = Array.from(
        document.querySelectorAll('[class*="comment"], [class*="Comment"], li, p')
      )
        .map((el) => normalize(el.textContent || ""))
        .filter((t) => t.length >= 4 && t.length <= 160)
        .filter((t) => !/^赞|回复|展开|收起|查看更多/.test(t));

      const stateComments = [];
      const stateDetails = [];
      const states = [window.__INITIAL_STATE__, window.__INITIAL_SSR_STATE__, window.__NEXT_DATA__];
      const queue = [];
      for (const st of states) {
        if (st && typeof st === "object") queue.push({ v: st, p: "root" });
      }
      let visited = 0;
      while (queue.length && visited < 6000) {
        const item = queue.shift();
        visited += 1;
        if (!item) continue;
        const { v, p } = item;
        if (v == null) continue;
        if (typeof v === "string") {
          const txt = normalize(v);
          const path = String(p || "").toLowerCase();
          if (!txt) continue;
          if (/comment|评论/.test(path) && txt.length >= 4 && txt.length <= 180) {
            if (!isBlockedText(txt)) stateComments.push(txt);
          }
          if (/(desc|content|text|note|title|caption|post|body|detail)/.test(path) && txt.length >= 16 && txt.length <= 1400) {
            if (!isBlockedText(txt)) stateDetails.push(txt);
          }
          continue;
        }
        if (Array.isArray(v)) {
          for (let i = 0; i < v.length && i < 40; i += 1) {
            queue.push({ v: v[i], p: `${p}[${i}]` });
          }
          continue;
        }
        if (typeof v === "object") {
          for (const [k, val] of Object.entries(v)) {
            queue.push({ v: val, p: `${p}.${k}` });
          }
        }
      }

      for (const x of stateDetails.slice(0, 80)) pushDetail(x);
      const mergedDetails = unique(detailCandidates);
      mergedDetails.sort((a, b) => b.length - a.length);
      const detailText = mergedDetails[0] || "";

      const commentCountText =
        textOf('[class*="comment-count"]') || textOf('[class*="commentCount"]') || "";

      return {
        title,
        detail_text: detailText,
        comments_preview: unique([...domComments, ...stateComments]).slice(0, 8).join(" | "),
        comment_count_text: commentCountText,
        blocked_by_risk_page: blockedByRiskPage,
      };
    });

    console.log(JSON.stringify({ success: true, ...result }));
  } catch (err) {
    console.log(
      JSON.stringify({
        success: false,
        error: "detail_fetch_failed",
        message: String(err),
      })
    );
  } finally {
    if (browser) {
      try {
        await browser.close();
      } catch (_) {}
    }
  }
}

main();
