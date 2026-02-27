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

  let puppeteer = null;
  const candidates = [];
  if (process.env.XHS_PUPPETEER_REQUIRE) {
    candidates.push(process.env.XHS_PUPPETEER_REQUIRE);
  }
  candidates.push(path.resolve(__dirname, "..", "vendor", "xhs-mcp", "node_modules", "puppeteer"));
  candidates.push("puppeteer");

  let lastErr = null;
  for (const mod of candidates) {
    try {
      puppeteer = require(mod);
      break;
    } catch (err) {
      lastErr = err;
    }
  }
  if (!puppeteer) {
    console.log(
      JSON.stringify({
        success: false,
        error: "puppeteer_require_failed",
        message: String(lastErr || "cannot load puppeteer"),
        candidates,
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
    try {
      await page.goto(url, { waitUntil: "networkidle2", timeout: timeoutMs });
    } catch (_) {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    }
    await page
      .waitForSelector("main,article,[class*='note-content'],[class*='desc']", {
        timeout: Math.max(1500, Math.min(5000, Math.floor(timeoutMs / 4))),
      })
      .catch(() => null);
    await new Promise((r) => setTimeout(r, 1800));

    const result = await page.evaluate(() => {
      const textOf = (sel) => {
        const el = document.querySelector(sel);
        return (el && el.textContent ? el.textContent : "").trim();
      };
      const normalize = (s) => (s || "").replace(/\s+/g, " ").trim();
      const normalizeName = (s) => normalize(s).replace(/^@+/, "");
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
      const isLikelyCommentText = (t) => {
        if (!t) return false;
        if (t.length < 4 || t.length > 220) return false;
        if (/^赞|^回复|^展开|^收起|^查看更多/.test(t)) return false;
        return true;
      };
      const equalName = (a, b) => {
        const aa = normalizeName(a);
        const bb = normalizeName(b);
        if (!aa || !bb) return false;
        return aa === bb;
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
        if (t.length < 6 || t.length > 1800) return;
        if (isBlockedText(t)) return;
        detailCandidates.push(t);
      };
      pushDetail(metaDesc);
      pushDetail(textOf('[class*="note-content"]'));
      pushDetail(textOf('[class*="desc"]'));
      pushDetail(textOf('[class*="note-text"]'));
      pushDetail(textOf('[class*="noteText"]'));
      pushDetail(textOf("article"));
      for (const el of Array.from(document.querySelectorAll("main p, article p, [class*='content'] p")).slice(0, 50)) {
        pushDetail(el.textContent || "");
      }

      const authorCandidates = [];
      const pushAuthorCandidate = (s) => {
        const name = normalizeName(s);
        if (!name) return;
        if (name.length < 2 || name.length > 40) return;
        authorCandidates.push(name);
      };
      pushAuthorCandidate(textOf('[class*="author"] [class*="name"]'));
      pushAuthorCandidate(textOf('[class*="author-name"]'));
      pushAuthorCandidate(textOf('[class*="user"] [class*="name"]'));
      pushAuthorCandidate(textOf('[class*="nickname"]'));

      const commentEntries = [];
      const pushCommentEntry = ({ text, actorName = "", hasAuthorBadge = false, isAuthorFlag = false }) => {
        const content = normalize(text);
        if (!isLikelyCommentText(content)) return;
        if (isBlockedText(content)) return;
        commentEntries.push({
          text: content,
          actorName: normalizeName(actorName),
          hasAuthorBadge: Boolean(hasAuthorBadge),
          isAuthorFlag: Boolean(isAuthorFlag),
        });
      };

      const domCommentNodes = Array.from(
        document.querySelectorAll(
          '[class*="comment-item"], [class*="commentItem"], [class*="comment"], li[class*="comment"], li'
        )
      ).slice(0, 160);
      for (const el of domCommentNodes) {
        const text = normalize(el.textContent || "");
        if (!isLikelyCommentText(text)) continue;
        const actorName = normalize(
          el.querySelector('[class*="name"], [class*="user"], [class*="author"], a')?.textContent || ""
        );
        const hasAuthorBadge = /作者|楼主|博主|贴主/.test(text);
        pushCommentEntry({ text, actorName, hasAuthorBadge, isAuthorFlag: false });
      }

      const stateDetails = [];
      const states = [window.__INITIAL_STATE__, window.__INITIAL_SSR_STATE__, window.__NEXT_DATA__];
      const queue = [];
      for (const st of states) {
        if (st && typeof st === "object") queue.push({ v: st, p: "root" });
      }
      let visited = 0;
      while (queue.length && visited < 7000) {
        const item = queue.shift();
        visited += 1;
        if (!item) continue;
        const { v, p } = item;
        if (v == null) continue;

        if (typeof v === "string") {
          const txt = normalize(v);
          const path = String(p || "").toLowerCase();
          if (!txt) continue;
          if (/(desc|content|text|note|title|caption|post|body|detail)/.test(path) && txt.length >= 6 && txt.length <= 1800) {
            if (!isBlockedText(txt)) stateDetails.push(txt);
          }
          if (
            /(author|creator|publisher|post_user|note_user|note\.user|nick|name)/.test(path) &&
            !/(comment|reply|replies)/.test(path)
          ) {
            pushAuthorCandidate(txt);
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
          const path = String(p || "").toLowerCase();
          if (/comment|reply|replies|评论/.test(path)) {
            const content =
              v.content || v.text || v.desc || v.comment || v.message || v.noteText || v.note_text || "";
            const actorName =
              (v.user && (v.user.nickName || v.user.nick_name || v.user.nickname || v.user.name)) ||
              v.nickName ||
              v.nick_name ||
              v.nickname ||
              v.userName ||
              v.user_name ||
              "";
            const tagText = `${v.tagText || ""} ${v.tag_text || ""} ${v.role || ""} ${v.userType || ""} ${v.user_type || ""}`;
            const isAuthorFlag = Boolean(
              v.isAuthor ||
              v.is_author ||
              v.isPoster ||
              v.is_poster ||
              v.isNoteAuthor ||
              v.is_note_author ||
              /author|poster|note_author|作者|楼主|博主|贴主/i.test(tagText)
            );
            pushCommentEntry({
              text: content,
              actorName,
              hasAuthorBadge: /作者|楼主|博主|贴主/.test(normalize(content)),
              isAuthorFlag,
            });
          }

          for (const [k, val] of Object.entries(v)) {
            queue.push({ v: val, p: `${p}.${k}` });
          }
        }
      }

      for (const x of stateDetails.slice(0, 80)) pushDetail(x);
      const mergedDetails = unique(detailCandidates);
      mergedDetails.sort((a, b) => b.length - a.length);
      const detailText = mergedDetails[0] || "";

      const candidateNames = unique(authorCandidates);
      const posterName = candidateNames[0] || "";
      const isPosterEntry = (entry) => {
        if (!entry || !entry.text) return false;
        if (entry.isAuthorFlag || entry.hasAuthorBadge) return true;
        if (posterName && entry.actorName && equalName(entry.actorName, posterName)) return true;
        if (posterName && entry.text.includes(posterName) && /作者|楼主|博主|贴主|回复/.test(entry.text)) return true;
        return false;
      };
      const allComments = unique(commentEntries.map((x) => x.text)).slice(0, 8);
      const posterComments = unique(commentEntries.filter(isPosterEntry).map((x) => x.text)).slice(0, 8);

      const commentCountText =
        textOf('[class*="comment-count"]') || textOf('[class*="commentCount"]') || "";

      return {
        title,
        detail_text: detailText,
        poster_comments_preview: posterComments.join(" | "),
        comments_preview: allComments.join(" | "),
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
