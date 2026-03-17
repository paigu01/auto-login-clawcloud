import os
import time
import pyotp
import requests
import urllib.parse
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth 

# ========== PushPlus 通知函数 ==========
def send_pushplus(token, title, content):
    if not token:
        print("⚠️ 未配置 PUSHPLUS_TOKEN，跳过微信通知。")
        return
    
    safe_title = urllib.parse.quote(title)
    safe_content = urllib.parse.quote(content)
    url = f"https://www.pushplus.plus/send?token={token}&title={safe_title}&content={safe_content}&template=html"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("📢 PushPlus 通知发送成功！")
        else:
            print(f"⚠️ PushPlus 发送异常: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ PushPlus 请求失败: {e}")

# ========== 主运行函数 ==========
def run_login():
    username = os.environ.get("GH_USERNAME")
    password = os.environ.get("GH_PASSWORD")
    totp_secret = os.environ.get("GH_2FA_SECRET")
    pushplus_token = os.environ.get("PUSHPLUS_TOKEN")

    current_step = "初始化"
    error_log = ""
    is_success = False

    if not username or not password:
        error_log = "未设置 GitHub 账号密码环境变量。"
        print(f"❌ 错误: {error_log}")
        send_pushplus(pushplus_token, "❌ ClawCloud 登录失败", error_log)
        return

    try:
        with sync_playwright() as p:
            # 既然不需要截图看界面，开启 headless=True 更节省云端资源
            browser = p.chromium.launch(
                headless=True, 
                args=["--disable-blink-features=AutomationControlled"]
            )
            context = browser.new_context(viewport={'width': 1920, 'height': 1080})
            page = context.new_page()

            Stealth().apply_stealth_sync(page)

            # 1. 访问主页
            current_step = "访问 ClawCloud 主页"
            print(f"🚀 [Step 1] {current_step}...")
            page.goto("https://ap-northeast-1.run.claw.cloud/")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            # 2. 点击 GitHub 按钮
            current_step = "点击 GitHub 登录按钮"
            print(f"🔍 [Step 2] {current_step}...")
            login_button = page.locator("button.chakra-button:has-text('GitHub')")
            if login_button.count() > 0:
                login_button.first.evaluate("el => el.click()")
            page.wait_for_timeout(3000)

            # 3. 填写 GitHub 账号密码
            current_step = "填写 GitHub 账号密码"
            print(f"⏳ [Step 3] {current_step}...")
            page.wait_for_url(lambda url: "github.com" in url, timeout=15000)
            if "login" in page.url:
                page.fill("#login_field", username)
                page.fill("#password", password)
                page.click("input[name='commit']")
                page.wait_for_timeout(3000)

            # 4. 处理 2FA
            current_step = "处理 GitHub 2FA 验证"
            print(f"🔐 [Step 4] {current_step}...")
            page.wait_for_timeout(3000)
            if "two-factor" in page.url or page.locator("#app_totp").count() > 0:
                if totp_secret:
                    token = pyotp.TOTP(totp_secret).now()
                    page.fill("#app_totp", token)
                    try:
                        page.locator("button:has-text('Verify')").click(timeout=3000)
                    except:
                        pass
                    page.wait_for_timeout(4000)
                else:
                    error_log = "检测到 2FA 页面，但未配置 GH_2FA_SECRET 环境变量！"
                    raise Exception(error_log)

            # 5. 处理授权页 (Authorize)
            current_step = "处理 GitHub OAuth 授权页面"
            print(f"⚠️ [Step 5] {current_step}...")
            if "authorize" in page.url.lower() or page.locator("#js-oauth-authorize-btn").count() > 0:
                auth_btn = page.locator("button[name='authorize_app'], #js-oauth-authorize-btn, button:has-text('Authorize')")
                if auth_btn.count() > 0:
                    auth_btn.first.click(timeout=5000)
                page.wait_for_timeout(4000)

            # 6. 等待最终跳转结果
            current_step = "验证最终登录结果"
            print(f"⏳ [Step 6] {current_step}...")
            page.wait_for_timeout(15000)
            final_url = page.url

            # 验证结果
            if page.get_by_text("App Launchpad").count() > 0 or "console" in final_url or "private-team" in final_url:
                is_success = True
            elif "signin" not in final_url and "github.com" not in final_url:
                is_success = True
            else:
                error_log = f"最后停留在未知的 URL: {final_url}，未检测到成功标志。"

            browser.close()

    except Exception as e:
        error_log = str(e)
        print(f"⚠️ 发生异常: {error_log}")

    # ========== 结束前发送推送通知 ==========
    if is_success:
        title = "✅ ClawCloud 登录成功"
        content = "🎉 恭喜！自动化脚本已成功完成 ClawCloud 的登录保活。"
        print(title)
        send_pushplus(pushplus_token, title, content)
    else:
        title = "❌ ClawCloud 登录失败"
        content = f"""
        😭😭😭 <b>登录保活任务失败！</b><br><br>
        <b>💥 失败所在步骤：</b><br>{current_step}<br><br>
        <b>⚠️ 错误日志/原因：</b><br>{error_log if error_log else '未能成功跳转到控制台页面'}
        """
        print(title)
        send_pushplus(pushplus_token, title, content)
        exit(1)

if __name__ == "__main__":
    run_login()
