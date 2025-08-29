from playwright.sync_api import sync_playwright, expect

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            print('Navigating to http://localhost:8000...')
            page.goto('http://localhost:8000', timeout=60000)

            # Wait for the main container to be visible
            expect(page.locator("div.container")).to_be_visible()

            print('Page loaded. Taking screenshot...')
            page.screenshot(path='/app/final_frontend.jpg', type='jpeg', quality=90, full_page=True)
            print('Screenshot saved as /app/final_frontend.jpg')
        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
