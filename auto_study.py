"""
超星学习通自动刷课脚本
流程：点击「2 视频」→ 播放视频 → 等待100% → 点击右侧列表下一个知识点 → 循环
"""

import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

URL = (
    "粘贴你的课程播放页链接"
)

POLL_INTERVAL = 5
LOGIN_WAIT = 300
MAX_CHAPTERS = 200


def log(msg: str):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def wait_for_login(page):
    log("请在浏览器中完成登录（扫码或输入账号密码）...")
    try:
        page.wait_for_url("**/mycourse/studentstudy**", timeout=LOGIN_WAIT * 1000)
        log("登录成功，已进入课程页面")
    except PwTimeout:
        log("等待登录超时，请重新运行脚本")
        sys.exit(1)


def click_video_tab(page):
    """
    点击顶部「2 视频」标签。
    跳转到新知识点后 iframe 会重新加载，需要等待和重试。
    元素位置可能在主页面或 iframe 中。
    """
    for attempt in range(6):
        if attempt > 0:
            log(f"等待「2 视频」标签出现... (第{attempt+1}次)")
            page.wait_for_timeout(3000)

        # 在主页面和所有 frame 中查找 span.spanText 包含"视频"
        targets = [page] + [f for f in page.frames if f != page.main_frame]
        for target in targets:
            try:
                spans = target.query_selector_all("span.spanText")
                for span in spans:
                    text = span.text_content().strip()
                    if "视频" in text:
                        span.click()
                        log(f"点击了「{text}」标签")
                        page.wait_for_timeout(3000)
                        return True
            except Exception:
                continue

            # 也找普通 span 中包含"视频"且短文本的
            try:
                spans = target.query_selector_all("span")
                for span in spans:
                    try:
                        text = span.text_content().strip()
                        if text in ("视频", "2 视频") and span.is_visible():
                            span.click()
                            log(f"点击了「{text}」标签")
                            page.wait_for_timeout(3000)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

    log("多次尝试后仍未找到「2 视频」标签")
    return False


def get_video_frame(page):
    """
    点击「2 视频」后，视频加载在 iframe(name=iframe) 的子 iframe 中。
    遍历所有 frame 找到包含 <video> 的那个。
    """
    page.wait_for_timeout(3000)

    for f in page.frames:
        try:
            has_video = f.evaluate("!!document.querySelector('video')")
            if has_video:
                log(f"找到视频 frame: {f.url[:80]}")
                return f
        except Exception:
            continue

    # 如果没找到，等一下再试（视频可能还在加载）
    log("视频未立即加载，等待 5 秒后重试...")
    page.wait_for_timeout(5000)

    for f in page.frames:
        try:
            has_video = f.evaluate("!!document.querySelector('video')")
            if has_video:
                log(f"找到视频 frame（第二次尝试）: {f.url[:80]}")
                return f
        except Exception:
            continue

    log("未找到包含 <video> 的 frame")
    return None


def click_play(frame):
    """点击播放按钮或通过 JS 播放"""
    if not frame:
        return False

    # 先尝试 JS 直接播放
    try:
        frame.evaluate("""
            (() => {
                const v = document.querySelector('video');
                if (v) { v.play(); return true; }
                return false;
            })()
        """)
        log("通过 JS 调用 video.play()")
        return True
    except Exception:
        pass

    # 再尝试点击播放按钮
    selectors = [
        ".vjs-big-play-button",
        ".vjs-play-control",
        "button.vjs-play-control",
        "[class*='play']",
        "video",
    ]
    for sel in selectors:
        try:
            el = frame.query_selector(sel)
            if el and el.is_visible():
                el.click()
                log(f"点击了播放按钮: {sel}")
                return True
        except Exception:
            continue

    log("未找到播放按钮")
    return False


def ensure_playing(frame, page):
    """如果视频暂停了，先检查是否有答题弹窗，处理完再恢复播放"""
    if not frame:
        return
    try:
        paused = frame.evaluate("document.querySelector('video')?.paused")
        if paused:
            log("视频暂停，检查是否有答题弹窗...")
            # 先检查答题弹窗（视频暂停很可能是因为弹窗）
            quiz_found = handle_quiz(page, frame)
            if quiz_found:
                time.sleep(2)
            # 恢复播放
            try:
                frame.evaluate("document.querySelector('video').play()")
                time.sleep(1)
                still_paused = frame.evaluate("document.querySelector('video')?.paused")
                if still_paused:
                    click_play(frame)
                else:
                    log("已恢复播放")
            except Exception:
                click_play(frame)
    except Exception:
        pass


def get_progress(frame):
    """获取播放进度百分比"""
    if not frame:
        return -1
    try:
        return frame.evaluate("""
            (() => {
                const v = document.querySelector('video');
                if (v && v.duration > 0)
                    return Math.floor((v.currentTime / v.duration) * 100);
                return -1;
            })()
        """)
    except Exception:
        return -1


def wait_video_finish(frame, page):
    """等待视频播放完成"""
    log("等待视频播放...")
    stale_count = 0
    last_progress = -1
    no_video_count = 0

    while True:
        # 如果 frame 失效（页面跳转），重新获取
        try:
            frame.evaluate("1")
        except Exception:
            log("视频 frame 失效，重新获取...")
            frame = get_video_frame(page)
            if not frame:
                log("重新获取视频 frame 失败，跳过")
                return True

        # 处理弹窗（传入视频 frame 以便精确检测）
        handle_popups(page, frame)

        ensure_playing(frame, page)
        progress = get_progress(frame)

        if progress >= 0:
            log(f"进度: {progress}%")
            no_video_count = 0
        else:
            no_video_count += 1
            if no_video_count <= 3:
                log("无法获取进度，视频可能未加载")
            if no_video_count > 12:
                log("持续无法获取进度，跳过此视频")
                return True

        if progress >= 98:
            log("视频播放完成！")
            return True

        if progress == last_progress:
            stale_count += 1
        else:
            stale_count = 0
        last_progress = progress

        if stale_count > 60:
            log("进度长时间无变化，跳过")
            return True

        time.sleep(POLL_INTERVAL)


def click_next_in_sidebar(page):
    """
    在右侧章节列表中，点击当前高亮项的下一个知识点。
    当前高亮项 class 包含: posCatalog_active
    知识点项 class 包含: posCatalog_select
    注意: nextElementSibling 可能是 catalog_points_yi（状态指示器），不是下一个知识点，
    所以需要收集所有 posCatalog_select，找到当前 active 的索引，然后点击 index+1。
    """
    result = page.evaluate("""
        (() => {
            // 收集所有知识点的可点击 span（带 onclick 的 span.posCatalog_name）
            const allNames = Array.from(document.querySelectorAll('.posCatalog_select .posCatalog_name'));
            if (allNames.length === 0)
                return { ok: false, msg: '未找到任何知识点（.posCatalog_name）' };

            // 找到当前高亮项：其父 div 带有 posCatalog_active
            let activeIdx = -1;
            for (let i = 0; i < allNames.length; i++) {
                if (allNames[i].closest('.posCatalog_active')) {
                    activeIdx = i;
                    break;
                }
            }

            if (activeIdx === -1)
                return { ok: false, msg: '未找到当前高亮项，共' + allNames.length + '个知识点' };

            const currentText = allNames[activeIdx].getAttribute('title') || allNames[activeIdx].textContent.trim().substring(0, 30);

            if (activeIdx >= allNames.length - 1)
                return { ok: false, msg: '「' + currentText + '」已是最后一个知识点' };

            // 点击下一个知识点的 span.posCatalog_name（它带有 onclick 事件）
            const nextName = allNames[activeIdx + 1];
            const nextText = nextName.getAttribute('title') || nextName.textContent.trim().substring(0, 30);
            nextName.click();

            return { ok: true, from: currentText, to: nextText, idx: activeIdx + 1, total: allNames.length };
        })()
    """)

    if result.get("ok"):
        log(f"从「{result['from']}」→「{result['to']}」({result['idx']+1}/{result['total']})")
        log("等待新页面加载...")
        page.wait_for_timeout(8000)
        return True
    else:
        log(result.get("msg", "未找到下一个知识点"))
        return False


def detect_quiz_in_frame(frame):
    """
    检测指定 frame 中是否存在答题弹窗。
    不依赖特定 class 名，而是检测通用特征：
    可见的 radio/checkbox，或包含"对""错""提交"文字的可见元素。
    """
    try:
        return frame.evaluate("""
            (() => {
                // 特征1: 有可见的 radio 或 checkbox
                const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
                let visibleInputs = 0;
                for (const inp of inputs) {
                    const rect = inp.getBoundingClientRect();
                    const parent = inp.closest('label, div, li, span');
                    if (rect.height > 0 || (parent && parent.offsetHeight > 0)) {
                        visibleInputs++;
                    }
                }
                if (visibleInputs >= 2) return true;

                // 特征2: 页面同时包含"对""错"和"提交"文字且可见
                const body = document.body ? document.body.innerText : '';
                if (body.includes('提交') && (body.includes('对') || body.includes('错') || body.includes('正确') || body.includes('错误'))) {
                    // 再确认有可见的提交按钮
                    const all = document.querySelectorAll('button, a, div, span, input');
                    for (const el of all) {
                        if (el.textContent.trim() === '提交' && el.offsetHeight > 0) return true;
                    }
                }

                // 特征3: 有可见的答题相关容器
                const quizSelectors = '.ans-videoquiz-wrap, .ans-timeDialog, .questionBox, [class*="videoquiz"], [class*="timu"]';
                const quiz = document.querySelector(quizSelectors);
                if (quiz && quiz.offsetHeight > 0) return true;

                return false;
            })()
        """)
    except Exception:
        return False


def handle_quiz(page, video_frame=None):
    """
    在所有 frame 中检测并处理答题弹窗。
    优先检查视频 frame（弹窗通常在视频 iframe 中）。
    """
    # 优先检查视频 frame
    frames_to_check = []
    if video_frame:
        frames_to_check.append(video_frame)
    frames_to_check.extend([f for f in page.frames if f != page.main_frame and f != video_frame])
    frames_to_check.append(page)

    for frame in frames_to_check:
        if not frame:
            continue
        try:
            if detect_quiz_in_frame(frame):
                log("检测到答题弹窗！开始答题...")
                _do_answer(frame, page)
                return True
        except Exception:
            continue

    return False


def _do_answer(frame, page):
    """
    作答判断题：先选「对」提交 → 如果错了改「错」再提交 → 关闭弹窗。
    """
    # 第一轮：选「对」
    log("选择「对」...")
    frame.evaluate("""
        (() => {
            // 找所有 radio/checkbox 及其 label
            const items = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
            const labels = document.querySelectorAll('label, li, div, span, p');

            // 方式1: 找包含"对"/"正确"/"√"文字的 label 并点击其 radio
            for (const label of labels) {
                const t = label.textContent.trim();
                if ((t === '对' || t === '正确' || t === '√' || t.startsWith('A')) && label.offsetHeight > 0) {
                    const radio = label.querySelector('input[type="radio"], input[type="checkbox"]');
                    if (radio) { radio.click(); return; }
                    label.click();
                    return;
                }
            }

            // 方式2: 直接点击第一个 radio
            for (const inp of items) {
                const parent = inp.closest('label, div, li');
                if (parent && parent.offsetHeight > 0) {
                    inp.click();
                    return;
                }
            }
            if (items.length >= 1) items[0].click();
        })()
    """)

    time.sleep(1)

    # 点击提交
    log("点击提交...")
    frame.evaluate("""
        (() => {
            const all = document.querySelectorAll('button, a, div, span, input[type="button"], input[type="submit"]');
            for (const el of all) {
                const t = el.textContent.trim();
                if (t === '提交' && el.offsetHeight > 0) { el.click(); return; }
            }
            // 备选 class 选择器
            const btn = document.querySelector('.ans-videoquiz-submit, [class*="submit"], .submitBtn');
            if (btn && btn.offsetHeight > 0) btn.click();
        })()
    """)

    time.sleep(2)

    # 检查是否答错
    wrong = False
    try:
        wrong = frame.evaluate("""
            (() => {
                const html = document.body ? document.body.innerHTML : '';
                if (html.includes('回答错误') || html.includes('答案错误') || html.includes('不正确') || html.includes('答错') || html.includes('wrong')) {
                    return true;
                }
                const icon = document.querySelector('[class*="wrong"], [class*="error"], [class*="Wrong"], .icon-wrong');
                if (icon && icon.offsetHeight > 0) return true;

                // 如果提交按钮还在且 radio 还可以选，说明可能答错可以重试
                const radios = document.querySelectorAll('input[type="radio"]:not(:checked)');
                const submitBtn = document.querySelector('.ans-videoquiz-submit, [class*="submit"]');
                if (radios.length > 0 && submitBtn && submitBtn.offsetHeight > 0) return true;

                return false;
            })()
        """)
    except Exception:
        pass

    if wrong:
        log("答案「对」错误，改选「错」重新提交...")
        frame.evaluate("""
            (() => {
                const labels = document.querySelectorAll('label, li, div, span, p');
                for (const label of labels) {
                    const t = label.textContent.trim();
                    if ((t === '错' || t === '错误' || t === '×' || t.startsWith('B')) && label.offsetHeight > 0) {
                        const radio = label.querySelector('input[type="radio"], input[type="checkbox"]');
                        if (radio) { radio.click(); return; }
                        label.click();
                        return;
                    }
                }
                // 点击第二个 radio
                const radios = document.querySelectorAll('input[type="radio"]');
                if (radios.length >= 2) radios[1].click();
            })()
        """)
        time.sleep(1)

        frame.evaluate("""
            (() => {
                const all = document.querySelectorAll('button, a, div, span, input[type="button"], input[type="submit"]');
                for (const el of all) {
                    const t = el.textContent.trim();
                    if (t === '提交' && el.offsetHeight > 0) { el.click(); return; }
                }
                const btn = document.querySelector('.ans-videoquiz-submit, [class*="submit"], .submitBtn');
                if (btn && btn.offsetHeight > 0) btn.click();
            })()
        """)
        time.sleep(2)
        log("已重新提交「错」")
    else:
        log("答案「对」正确！")

    # 关闭弹窗
    time.sleep(1)
    try:
        frame.evaluate("""
            (() => {
                const all = document.querySelectorAll('button, a, div, span, i');
                for (const el of all) {
                    const t = el.textContent.trim();
                    if ((t === '关闭' || t === '确定' || t === '×' || t === 'X' || t === '继续观看' || t === '继续') && el.offsetHeight > 0) {
                        el.click();
                        return;
                    }
                }
                const close = document.querySelector('.ans-videoquiz-close, [class*="close"], [class*="Close"]');
                if (close && close.offsetHeight > 0) close.click();
            })()
        """)
        log("关闭了答题弹窗")
    except Exception:
        pass

    # 也在主页面关闭可能的弹窗
    try:
        for sel in [".layui-layer-close", ".layui-layer-btn0"]:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                break
    except Exception:
        pass


def handle_popups(page, video_frame=None):
    """处理所有弹窗：答题弹窗 + 普通提示弹窗"""
    handle_quiz(page, video_frame)

    for sel in [".layui-layer-btn0", ".layui-layer-close"]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                log("关闭弹窗")
                page.wait_for_timeout(500)
        except Exception:
            continue


def run():
    with sync_playwright() as p:
        log("启动浏览器...")
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)
        page = context.new_page()
        try:
            page.goto(URL, timeout=60000)
        except Exception:
            pass

        time.sleep(3)
        log(f"当前页面: {page.url[:80]}")

        if "passport" in page.url or "login" in page.url.lower():
            wait_for_login(page)
        else:
            log("已在登录状态，直接进入课程")

        page.wait_for_timeout(5000)
        log("=== 开始自动刷课 ===")

        for idx in range(MAX_CHAPTERS):
            log(f"\n{'='*40}")
            log(f"第 {idx + 1} 个知识点")
            log(f"{'='*40}")

            handle_popups(page)
            page.wait_for_timeout(2000)

            # 步骤1: 点击「2 视频」标签
            click_video_tab(page)
            page.wait_for_timeout(3000)

            # 步骤2: 找到视频 frame
            video_frame = get_video_frame(page)

            # 步骤3: 播放视频
            if video_frame:
                click_play(video_frame)
                page.wait_for_timeout(2000)

                # 步骤4: 等待视频播放完成
                wait_video_finish(video_frame, page)
            else:
                log("此知识点无视频或视频加载失败，跳过")

            page.wait_for_timeout(2000)
            handle_popups(page)

            # 步骤5: 点击右侧列表的下一个知识点
            if not click_next_in_sidebar(page):
                log("已到最后一个知识点，刷课结束！")
                break

            page.wait_for_timeout(5000)

        log("\n=== 刷课完毕 ===")
        try:
            input("按 Enter 关闭浏览器...")
        except EOFError:
            page.wait_for_timeout(60000)
        browser.close()


if __name__ == "__main__":
    run()
