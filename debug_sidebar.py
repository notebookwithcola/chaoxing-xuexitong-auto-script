"""调试：打印右侧章节列表的完整 DOM 结构"""
import time, sys
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

URL = (
    "粘贴你的课程播放页链接"
)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(viewport={"width": 1400, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => false });")
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)

        if "passport" in page.url or "login" in page.url.lower():
            print("请登录...")
            try:
                page.wait_for_url("**/mycourse/studentstudy**", timeout=300000)
            except PwTimeout:
                sys.exit(1)

        page.wait_for_timeout(8000)

        # 打印当前 active 项和下一项的完整 outerHTML
        info = page.evaluate("""
            (() => {
                const results = [];
                const allSelect = Array.from(document.querySelectorAll('.posCatalog_select'));
                results.push('共 ' + allSelect.length + ' 个 .posCatalog_select');

                let activeIdx = -1;
                for (let i = 0; i < allSelect.length; i++) {
                    if (allSelect[i].classList.contains('posCatalog_active')) {
                        activeIdx = i;
                        break;
                    }
                }
                results.push('active 索引: ' + activeIdx);

                // 打印 active 项和它后面2个的完整 outerHTML
                for (let i = Math.max(0, activeIdx); i < Math.min(allSelect.length, activeIdx + 3); i++) {
                    results.push('\\n--- [' + i + '] class=' + allSelect[i].className + ' ---');
                    results.push(allSelect[i].outerHTML.substring(0, 500));
                }

                // 打印 active 项的父元素结构
                if (activeIdx >= 0) {
                    const active = allSelect[activeIdx];
                    results.push('\\n--- active 父元素 ---');
                    results.push('parent tag=' + active.parentElement.tagName + ' class=' + active.parentElement.className);
                    results.push('parent children count=' + active.parentElement.children.length);
                    // 列出父元素的所有子元素
                    for (let i = 0; i < Math.min(active.parentElement.children.length, 10); i++) {
                        const child = active.parentElement.children[i];
                        results.push('  child[' + i + '] tag=' + child.tagName + ' class=' + child.className.substring(0, 60) + ' text=' + child.textContent.trim().substring(0, 30));
                    }
                }

                return results.join('\\n');
            })()
        """)
        print(info)

        try:
            input("\n按 Enter 关闭...")
        except EOFError:
            pass
        browser.close()

if __name__ == "__main__":
    run()
