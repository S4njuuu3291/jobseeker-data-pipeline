import asyncio
import os
import random
from typing import Dict, TypedDict

from playwright.async_api import Page, Browser, BrowserContext, ViewportSize


class DeviceProfile(TypedDict):
    user_agent: str
    viewport: ViewportSize
    device_scale_factor: float
    is_mobile: bool
    has_touch: bool


DEVICE_PROFILES: Dict[str, DeviceProfile] = {
    "desktop_chrome": {
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "viewport": {"width": 1920, "height": 1080},
        "device_scale_factor": 1.0,
        "is_mobile": False,
        "has_touch": False,
    }
}

# ============================================================================
# STEALTH FUNCTIONS: Human-like Behavior
# ============================================================================


async def human_delay(min_ms: int = 50, max_ms: int = 150) -> None:
    """Jeda jitter singkat untuk efisiensi tinggi."""
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def fast_human_scroll(page: Page):
    """Scroll instan untuk trigger lazy loading tanpa buang waktu."""
    y_offset = random.randint(500, 1500)
    await page.mouse.wheel(0, y_offset)
    await asyncio.sleep(0.3)


# ============================================================================
# STEALTH BROWSER CONTEXT (The Fixer)
# ============================================================================


async def create_browser(p, headless: bool = True):
    """Create browser with Lambda-safe configuration."""
    slow_mo = 200 if not headless else 0
    is_lambda = os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None

    # Base arguments that work reliably
    args = [
        "--disable-blink-features=AutomationControlled",
        "--use-fake-ui-for-media-stream",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-dev-tools",
        "--disable-client-side-phishing-detection",
        "--disable-cloud-import",
        "--disable-component-extensions-with-background-pages",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-features=Translate",
        "--disable-sync",
    ]

    # Add Lambda-specific args for stability
    if is_lambda:
        args.append("--single-process")
        args.append("--no-zygote")

    try:
        browser = await p.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=args,
        )
        return browser
    except Exception as e:
        print(f"ERROR: Failed to launch browser: {type(e).__name__}: {str(e)}")
        raise


async def create_stealth_context(
    browser: Browser,
    profile: str = "desktop_chrome",
) -> BrowserContext:
    device = DEVICE_PROFILES[profile]

    context = await browser.new_context(
        user_agent=device["user_agent"],
        viewport=device["viewport"],
        device_scale_factor=device["device_scale_factor"],
        is_mobile=device["is_mobile"],
        has_touch=device["has_touch"],
        locale="en-US",
        timezone_id="America/New_York",
        permissions=["geolocation", "notifications"],
    )

    # CRITICAL: Injeksi script SEBELUM page load
    # Script ini HARUS jalan sebelum page js berjalan
    await context.add_init_script(
        """
        // BLOCK 1: DESTROY WEBDRIVER DETECTION (Multiple vectors)
        // ====================================================

        // Vector 1: Direct navigator.webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,  // Return false, bukan undefined
            configurable: false,
            enumerable: false
        });

        // Vector 2: Remove from prototype chain
        delete Object.getPrototypeOf(navigator).webdriver;

        // Vector 3: Proxy navigator untuk intercept semua property access
        const handler = {
            get: (target, prop) => {
                if (prop === 'webdriver') return false;
                return target[prop];
            }
        };
        const proxiedNavigator = new Proxy(navigator, handler);

        // Vector 4: Override toString
        const originalToString = ({}).toString;
        Object.defineProperty(Object.prototype, 'toString', {
            value: originalToString,
            writable: true,
            enumerable: false,
            configurable: true
        });


        // BLOCK 2: FIX PLUGINARRAY - Direct manipulation
        // ====================================================

        // Create mock plugins sebagai array biasa
        const mockPlugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format', version: '' },
            { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format', version: '' },
            { name: 'Native Client Executable', filename: 'internal-nacl-plugin', description: '', version: '' }
        ];

        // Add methods
        mockPlugins.item = function(i) { return this[i] || null; };
        mockPlugins.namedItem = function(name) {
            for (let i = 0; i < this.length; i++) {
                if (this[i].name === name) return this[i];
            }
            return null;
        };
        mockPlugins.refresh = function() {};

        // KRUSIAL: Try to make it instanceof PluginArray
        try {
            // Attempt 1: Set prototype to PluginArray.prototype
            if (PluginArray && PluginArray.prototype) {
                Object.setPrototypeOf(mockPlugins, PluginArray.prototype);
            }
        } catch (e) {
            // Fallback: Set Symbol.toStringTag
            Object.defineProperty(mockPlugins, Symbol.toStringTag, {
                value: 'PluginArray'
            });
        }

        // Override navigator.plugins dengan Proxy
        Object.defineProperty(navigator, 'plugins', {
            value: new Proxy(mockPlugins, {
                get(target, prop) {
                    if (prop === 'length') return target.length || 3;
                    if (prop === Symbol.toStringTag) return 'PluginArray';
                    if (typeof prop === 'symbol') return target[prop];
                    if (!isNaN(prop)) return target[parseInt(prop)];
                    return target[prop];
                }
            }),
            configurable: false,
            writable: false
        });


        // BLOCK 3: FIX MIME TYPES
        // ====================================================

        const mockMimeTypes = [
            {
                type: 'application/x-google-chrome-pdf',
                suffixes: 'pdf',
                description: 'Portable Document Format',
                enabledPlugin: mockPlugins[0]
            }
        ];

        mockMimeTypes.item = (i) => mockMimeTypes[i] || null;
        mockMimeTypes.namedItem = (name) => {
            for (let i = 0; i < mockMimeTypes.length; i++) {
                if (mockMimeTypes[i].type === name) return mockMimeTypes[i];
            }
            return null;
        };

        Object.defineProperty(navigator, 'mimeTypes', {
            value: mockMimeTypes,
            configurable: false,
            writable: false
        });


        // BLOCK 4: CHROME OBJECT
        // ====================================================

        window.chrome = {
            runtime: {
                id: 'chrome-id-placeholder',
                getManifest: () => ({}),
                getURL: (s) => s,
                connect: () => ({}),
                sendMessage: () => ({}),
                onConnect: { addListener: () => {} },
                onMessage: { addListener: () => {} }
            },
            app: {},
            webstore: {}
        };

        Object.defineProperty(window, 'chrome', {
            value: window.chrome,
            writable: false,
            configurable: false
        });


        // BLOCK 5: PERMISSIONS
        // ====================================================

        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = (params) => {
            if (params.name === 'notifications') {
                return Promise.resolve({state: 'denied'});
            }
            return originalQuery.call(navigator.permissions, params);
        };

        // BLOCK 6: LANGUAGES
        // ====================================================

        Object.defineProperty(navigator, 'languages', {
            value: ['en-US', 'en'],
            configurable: false
        });
    """
    )

    return context

def normalize_url(url: str) -> str:
    """Buang parameter tracking dari URL job agar hash konsisten."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, '', '', ''))
