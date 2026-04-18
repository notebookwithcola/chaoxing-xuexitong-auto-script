"""调试脚本：登录后打印页面的 iframe 结构和关键元素，帮助定位选择器"""

import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

URL = (输入你的课程视频播放页链接
)

def run():
    with sync_playwright() as p:
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
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        if "passport" in page.url or "login" in page.url.lower():
            print("请在浏览器中登录...")
            try:
                page.wait_for_url("**/mycourse/studentstudy**", timeout=300000)
                print("登录成功！")
            except PwTimeout:
                print("登录超时")
                sys.exit(1)

        print("等待页面加载...")
        page.wait_for_timeout(8000)

        print("\n" + "=" * 80)
        print("【1】所有 frames 列表：")
        print("=" * 80)
        for i, f in enumerate(page.frames):
            print(f"  Frame[{i}]: name={f.name!r}, url={f.url[:120]}")

        print("\n" + "=" * 80)
        print("【2】主页面中查找关键元素：")
        print("=" * 80)
        debug_elements(page, "主页面")

        print("\n" + "=" * 80)
        print("【3】逐个 frame 中查找关键元素：")
        print("=" * 80)
        for i, f in enumerate(page.frames):
            if f == page.main_frame:
                continue
            print(f"\n--- Frame[{i}]: {f.url[:100]} ---")
            debug_elements(f, f"Frame[{i}]")

        print("\n" + "=" * 80)
        print("【4】右侧章节列表结构：")
        print("=" * 80)
        try:
            sidebar_info = page.evaluate("""
                (() => {
                    const results = [];
                    // 查找所有可能的章节列表项
                    const selectors = [
                        '.chapter_item',
                        '.catalog_points_sa',
                        '.catalog_points_yi',
                        '.posCatalog_active',
                        '.currents',
                        '[class*="catalog"]',
                        '[class*="chapter"]',
                        '.jx_mItemActive',
                        '.ncells .cells li',
                        '.ncells li',
                        '.prevmark li',
                    ];
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 0) {
                            results.push('选择器 ' + sel + ' => 找到 ' + els.length + ' 个');
                            for (let j = 0; j < Math.min(els.length, 5); j++) {
                                const el = els[j];
                                results.push('  [' + j + '] class=' + el.className.substring(0, 80) + ' text=' + el.textContent.trim().substring(0, 40));
                            }
                        }
                    }
                    if (results.length === 0) results.push('未找到任何章节列表项');
                    return results.join('\\n');
                })()
            """)
            print(sidebar_info)
        except Exception as e:
            print(f"查找章节列表出错: {e}")

        print("\n完成调试。按 Enter 关闭浏览器...")
        input()
        browser.close()


def debug_elements(frame, label):
    """在指定 frame 中查找关键元素并打印"""
    checks = [
        ("video 标签", "video"),
        ("视频文字", "*:has-text('视频')"),
        ("2 视频", "*:has-text('2 视频')"),
        ("播放按钮 vjs-big-play-button", ".vjs-big-play-button"),
        ("播放控制 vjs-play-control", ".vjs-play-control"),
        ("video-js 容器", ".video-js"),
        ("iframe 子标签", "iframe"),
        ("ans-attach-ct", ".ans-attach-ct"),
        ("tabtag", ".tabtag"),
        ("prev_tab", ".prev_tab"),
    ]
    for name, sel in checks:
        try:
            els = frame.query_selector_all(sel)
            visible = sum(1 for e in els if e.is_visible())
            if els:
                texts = []
                for e in els[:3]:
                    try:
                        t = e.text_content()
                        texts.append(t.strip()[:40] if t else "(空)")
                    except:
                        texts.append("(无法获取)")
                print(f"  {name}: 共{len(els)}个(可见{visible}) => {texts}")
        except Exception:
            pass

    # 用 JS 找含"视频"文字的所有叶子元素
    try:
        video_texts = frame.evaluate("""
            (() => {
                const results = [];
                const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                while (walk.nextNode()) {
                    const t = walk.currentNode.textContent.trim();
                    if (t.includes('视频') && t.length < 20) {
                        const parent = walk.currentNode.parentElement;
                        if (parent) {
                            results.push({
                                tag: parent.tagName,
                                cls: parent.className.substring(0, 60),
                                text: t,
                                visible: parent.offsetHeight > 0,
                            });
                        }
                    }
                }
                return results.slice(0, 10);
            })()
        """)
        if video_texts:
            print(f"  [JS] 含「视频」文字的元素:")
            for vt in video_texts:
                print(f"    <{vt['tag']} class=\"{vt['cls']}\"> \"{vt['text']}\" visible={vt['visible']}")
    except Exception:
        pass


if __name__ == "__main__":
    run()
