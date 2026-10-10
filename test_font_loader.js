const assert = require('node:assert/strict');
const test = require('node:test');

const FontLoader = require('./font-loader.js');

const BUNDLE_SHA256 = '4bf5122f344554c53bde2ebb8cd2b7e3d1600ad631c385a5d7cce23c7785459a';

class CacheTestLoader extends FontLoader {
  constructor(installedVersion, installedBundleSha256) {
    super();
    this.testInstalledVersion = installedVersion;
    this.testInstalledBundleSha256 = installedBundleSha256;
    this.savedVersion = null;
  }

  async getInstalledBundleMetadata() {
    return {
      key: 'version',
      value: this.testInstalledVersion,
      bundleSha256: this.testInstalledBundleSha256,
    };
  }

  async loadCatalogFromDB() {
    return { fonts: [{ id: 'cached-font' }] };
  }

  async extractBundle() {}

  async saveCatalog() {}

  async setInstalledVersion(version, versionDate, bundleSha256) {
    this.savedVersion = { version, versionDate, bundleSha256 };
  }
}

function jsonResponse(body) {
  return {
    ok: true,
    async json() {
      return body;
    },
  };
}

function bundleResponse() {
  let delivered = false;
  return {
    ok: true,
    headers: {
      get(name) {
        return name === 'content-length' ? '1' : null;
      },
    },
    body: {
      getReader() {
        return {
          async read() {
            if (delivered) return { done: true };
            delivered = true;
            return { done: false, value: new Uint8Array([1]) };
          },
        };
      },
    },
  };
}

test('load downloads a changed bundle when its version is unchanged', async (t) => {
  const requested = [];
  const originalFetch = global.fetch;
  t.after(() => {
    global.fetch = originalFetch;
  });

  global.fetch = async (url) => {
    requested.push(url);
    if (url.endsWith('/manifest.json')) {
      return jsonResponse({
        version: 7,
        version_date: '2026-08-23T00:00:00Z',
        bundle_size: 1,
        bundle_sha256: BUNDLE_SHA256,
      });
    }
    if (url.endsWith('/fonts.json')) {
      return jsonResponse({ fonts: [] });
    }
    return bundleResponse();
  };

  const loader = new CacheTestLoader(7, 'old-sha');

  assert.equal(await loader.load('/bundle'), true);
  assert.deepEqual(requested, [
    '/bundle/manifest.json',
    '/bundle/fonts.json',
    '/bundle/fonts.zip',
  ]);
  assert.deepEqual(loader.savedVersion, {
    version: 7,
    versionDate: '2026-08-23T00:00:00Z',
    bundleSha256: BUNDLE_SHA256,
  });
});

test('load rejects a bundle whose bytes do not match the manifest sha256', async (t) => {
  const originalFetch = global.fetch;
  t.after(() => {
    global.fetch = originalFetch;
  });

  let extracted = false;
  class CorruptBundleLoader extends CacheTestLoader {
    async extractBundle() {
      extracted = true;
    }
  }

  global.fetch = async (url) => {
    if (url.endsWith('/manifest.json')) {
      return jsonResponse({
        version: 7,
        version_date: '2026-08-23T00:00:00Z',
        bundle_size: 1,
        bundle_sha256: 'deadbeef',
      });
    }
    if (url.endsWith('/fonts.json')) {
      return jsonResponse({ fonts: [] });
    }
    return bundleResponse();
  };

  const loader = new CorruptBundleLoader(6, null);

  await assert.rejects(loader.load('/bundle'), /integrity/i);
  assert.equal(extracted, false);
  assert.equal(loader.savedVersion, null);
});

test('load reuses cache when both version and bundle hash match', async (t) => {
  const requested = [];
  const originalFetch = global.fetch;
  t.after(() => {
    global.fetch = originalFetch;
  });

  global.fetch = async (url) => {
    requested.push(url);
    return jsonResponse({ version: 7, bundle_sha256: 'same-sha' });
  };

  const loader = new CacheTestLoader(7, 'same-sha');

  assert.equal(await loader.load('/bundle'), false);
  assert.deepEqual(requested, ['/bundle/manifest.json']);
  assert.deepEqual(loader.getAllFonts(), [{ id: 'cached-font' }]);
});

// ---------------------------------------------------------------------------
// registerFont lifecycle: idempotent re-registration, replacement on option
// change, and teardown on clearCache. These need a minimal fake DOM because
// registerFont appends a <style> element and creates blob URLs.
// ---------------------------------------------------------------------------

function fakeBrowserEnvironment() {
  const createdStyleElements = [];
  const appendedStyleElements = [];
  const createdObjectUrls = [];
  const revokedObjectUrls = [];

  const makeStyleElement = () => {
    const el = {
      textContent: '',
      removed: false,
      remove() {
        this.removed = true;
      },
    };
    createdStyleElements.push(el);
    return el;
  };

  const head = {
    children: appendedStyleElements,
    appendChild(el) {
      appendedStyleElements.push(el);
      return el;
    },
  };

  const originalDocument = global.document;
  const originalURL = global.URL;
  const originalIndexedDB = global.indexedDB;

  global.document = { createElement: makeStyleElement, head };
  global.URL = {
    createObjectURL() {
      const url = `blob:fake-${createdObjectUrls.length}`;
      createdObjectUrls.push(url);
      return url;
    },
    revokeObjectURL(url) {
      revokedObjectUrls.push(url);
    },
  };
  global.indexedDB = {
    deleteDatabase() {
      const request = {};
      queueMicrotask(() => request.onsuccess());
      return request;
    },
  };

  return {
    createdStyleElements,
    appendedStyleElements,
    createdObjectUrls,
    revokedObjectUrls,
    restore() {
      global.document = originalDocument;
      global.URL = originalURL;
      global.indexedDB = originalIndexedDB;
    },
  };
}

class RegistrationTestLoader extends FontLoader {
  constructor() {
    super();
    this.catalog = {
      fonts: [
        {
          id: '01-demo',
          name: 'Demo',
          dir_name: '01-demo',
          files: [{ filename: 'Demo-Regular.woff2' }],
        },
      ],
    };
  }

  async getFile() {
    return { size: 1 };
  }
}

test('registerFont is idempotent for repeated identical registrations', async (t) => {
  const env = fakeBrowserEnvironment();
  t.after(() => env.restore());

  const loader = new RegistrationTestLoader();

  assert.equal(await loader.registerFont('01-demo'), true);
  assert.equal(await loader.registerFont('01-demo'), true);
  assert.equal(await loader.registerFont('01-demo', 'Demo', { weight: 'normal' }), true);

  // One style element, one blob URL, and nothing revoked.
  assert.equal(env.appendedStyleElements.length, 1);
  assert.equal(env.createdObjectUrls.length, 1);
  assert.deepEqual(env.revokedObjectUrls, []);
  assert.equal(loader.registeredFonts.size, 1);
});

test('registerFont replaces the registration when its options change', async (t) => {
  const env = fakeBrowserEnvironment();
  t.after(() => env.restore());

  const loader = new RegistrationTestLoader();

  assert.equal(await loader.registerFont('01-demo'), true);
  assert.equal(await loader.registerFont('01-demo', 'Demo', { weight: 'bold' }), true);

  const [firstEl, secondEl] = env.appendedStyleElements;
  assert.equal(firstEl.removed, true, 'superseded style element is detached');
  assert.equal(secondEl.removed, false, 'current style element stays attached');
  assert.match(secondEl.textContent, /font-weight: bold/);
  assert.deepEqual(env.revokedObjectUrls, [env.createdObjectUrls[0]]);
  assert.equal(loader.registeredFonts.size, 1);
});

test('clearCache removes registrations and revokes their blob URLs', async (t) => {
  const env = fakeBrowserEnvironment();
  t.after(() => env.restore());

  const loader = new RegistrationTestLoader();
  assert.equal(await loader.registerFont('01-demo'), true);

  await loader.clearCache();

  assert.equal(env.appendedStyleElements[0].removed, true);
  assert.deepEqual(env.revokedObjectUrls, env.createdObjectUrls);
  assert.equal(loader.registeredFonts.size, 0);
});
