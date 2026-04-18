"""调试：登录后等待弹窗出现，然后打印弹窗的 DOM 结构"""
import time, sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

URL = (输入你的课程播放页链接
)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
        page = context.new_page()

        try:
            page.goto(URL, timeout=60000)
        except Exception:
            pass
        time.sleep(3)

        if "passport" in page.url or "login" in page.url.lower():
            print("请登录...")
            try:
                page.wait_for_url("**/mycourse/studentstudy**", timeout=300000)
            except PwTimeout:
                sys.exit(1)

        page.wait_for_timeout(5000)
        print("登录成功！")

        # 先点击「2 视频」
        try:
            spans = page.query_selector_all("span.spanText")
            for span in spans:
                if "视频" in span.text_content().strip():
                    span.click()
                    print("点击了视频标签")
                    break
        except Exception:
            pass

        page.wait_for_timeout(3000)

        # 找到视频 frame 并播放
        video_frame = None
        for f in page.frames:
            try:
                if f.evaluate("!!document.querySelector('video')"):
                    video_frame = f
                    break
            except:
                continue

        if video_frame:
            try:
                video_frame.evaluate("document.querySelector('video').play()")
                print("开始播放视频")
            except:
                pass

        print("\n等待弹窗出现... 弹窗出现后按 Enter 键进行调试扫描")
        print("（也可以直接按 Enter 立即扫描当前页面）")
        try:
            input()
        except EOFError:
            time.sleep(30)

        print("\n" + "=" * 80)
        print("开始扫描所有 frame 中的弹窗/答题元素")
        print("=" * 80)

        for i, f in enumerate(page.frames):
            try:
                info = f.evaluate("""
                    (() => {
                        const results = [];

                        // 1. 查找所有可见的 overlay/modal/dialog 元素
                        const overlays = document.querySelectorAll('[class*="quiz"], [class*="Quiz"], [class*="dialog"], [class*="Dialog"], [class*="modal"], [class*="Modal"], [class*="popup"], [class*="Popup"], [class*="layer"], [class*="Layer"], [class*="pop"], [class*="ans-"], [class*="question"], [class*="timu"], [class*="mask"]');
                        for (const el of overlays) {
                            if (el.offsetHeight > 0 && el.innerHTML.length < 3000) {
                                results.push('OVERLAY: <' + el.tagName + ' class="' + el.className.substring(0, 80) + '">');
                                results.push('  innerHTML(前500字): ' + el.innerHTML.substring(0, 500));
                            }
                        }

                        // 2. 查找 radio/checkbox
                        const inputs = document.querySelectorAll('input[type="radio"], input[type="checkbox"]');
                        for (const inp of inputs) {
                            if (inp.offsetHeight > 0 || (inp.parentElement && inp.parentElement.offsetHeight > 0)) {
                                const label = inp.closest('label') || inp.parentElement;
                                results.push('INPUT: type=' + inp.type + ' name=' + inp.name + ' text=' + (label ? label.textContent.trim().substring(0, 50) : ''));
                            }
                        }

                        // 3. 查找含"对/错/提交/判断"文字的可见元素
                        const keywords = ['对', '错', '提交', '判断', 'true', 'false', '正确', '错误'];
                        const all = document.querySelectorAll('span, div, button, a, label, li, p');
                        for (const el of all) {
                            const t = el.textContent.trim();
                            if (t.length <= 10 && t.length > 0) {
                                for (const kw of keywords) {
                                    if (t.includes(kw) && el.offsetHeight > 0) {
                                        results.push('TEXT: <' + el.tagName + ' class="' + el.className.substring(0, 60) + '"> "' + t + '"');
                                        break;
                                    }
                                }
                            }
                        }

                        // 4. 查找按钮
                        const btns = document.querySelectorAll('button, [class*="btn"], [class*="submit"], a[onclick]');
                        for (const btn of btns) {
                            if (btn.offsetHeight > 0) {
                                results.push('BTN: <' + btn.tagName + ' class="' + btn.className.substring(0, 60) + '"> "' + btn.textContent.trim().substring(0, 30) + '"');
                            }
                        }

                        return results.length > 0 ? results.join('\\n') : null;
                    })()
                """)
                if info:
                    print(f"\n--- Frame[{i}]: {f.url[:100]} ---")
                    print(info)
            except Exception:
                continue

        print("\n调试完成。")
        try:
            input("按 Enter 关闭...")
        except EOFError:
            pass
        browser.close()

if __name__ == "__main__":
    run()
