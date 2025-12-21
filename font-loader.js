/**
 * fontaine - Font Loader
 * 
 * Async font loader with IndexedDB caching, version management, and progress tracking.
 * Works in vanilla JavaScript - no build tools required.
 * 
 * Copyright © 2025 Noise Factor (https://noisefactor.io/)
 * MIT License
 * 
 * Usage:
 *   const loader = new FontLoader();
 *   
 *   await loader.load('./bundle', {
 *     onProgress: (percent, message) => console.log(`${percent}% ${message}`)
 *   });
 *   
 *   const monoFonts = loader.getFontsByTag('monospace');
 *   const quirkyFonts = loader.getFontsByTag('quirky');
 */

class FontLoader {
  constructor(options = {}) {
    this.dbName = options.dbName || 'fontaine';
    this.dbVersion = 1;
    this.db = null;
    this.catalog = null;
    this.installedVersion = null;
    this.fontsLoaded = false;
  }

  // =========================================================================
  // IndexedDB Management
  // =========================================================================

  async openDB() {
    if (this.db) return this.db;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = () => reject(request.error);

      request.onsuccess = () => {
        this.db = request.result;
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;

        // Store for bundle metadata
        if (!db.objectStoreNames.contains('meta')) {
          db.createObjectStore('meta', { keyPath: 'key' });
        }

        // Store for font catalog
        if (!db.objectStoreNames.contains('fonts')) {
          const fontStore = db.createObjectStore('fonts', { keyPath: 'id' });
          fontStore.createIndex('category', 'category', { unique: false });
          fontStore.createIndex('style', 'style', { unique: false });
        }

        // Store for font file blobs
        if (!db.objectStoreNames.contains('files')) {
          db.createObjectStore('files', { keyPath: 'path' });
        }
      };
    });
  }

  async getInstalledVersion() {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('meta', 'readonly');
      const store = tx.objectStore('meta');
      const request = store.get('version');
      request.onsuccess = () => resolve(request.result?.value || null);
      request.onerror = () => reject(request.error);
    });
  }

  async setInstalledVersion(version, versionDate, bundleSha256) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('meta', 'readwrite');
      const store = tx.objectStore('meta');
      store.put({ key: 'version', value: version, versionDate, bundleSha256 });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async saveCatalog(fonts) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('fonts', 'readwrite');
      const store = tx.objectStore('fonts');
      store.clear();
      fonts.forEach(font => store.put(font));
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async saveFile(path, blob) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('files', 'readwrite');
      const store = tx.objectStore('files');
      store.put({ path, blob });
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async getFile(path) {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('files', 'readonly');
      const store = tx.objectStore('files');
      const request = store.get(path);
      request.onsuccess = () => resolve(request.result?.blob || null);
      request.onerror = () => reject(request.error);
    });
  }

  async getAllFontsFromDB() {
    const db = await this.openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction('fonts', 'readonly');
      const store = tx.objectStore('fonts');
      const request = store.getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
  }

  // =========================================================================
  // Loading
  // =========================================================================

  /**
   * Load fonts from a bundle directory.
   * Downloads only if needed (version mismatch or force=true).
   * 
   * @param {string} bundlePath - Path to bundle directory
   * @param {Object} options
   * @param {boolean} options.force - Force re-download
   * @param {Function} options.onProgress - Progress callback (percent, message)
   * @returns {Promise<boolean>} - True if fonts were downloaded, false if cached
   */
  async load(bundlePath, options = {}) {
    const { force = false, onProgress = () => {} } = options;

    onProgress(0, 'Loading manifest...');

    // Fetch manifest
    const manifestRes = await fetch(`${bundlePath}/manifest.json`);
    if (!manifestRes.ok) {
      throw new Error(`Failed to load manifest: ${manifestRes.status}`);
    }
    const manifest = await manifestRes.json();
    const bundleVersion = manifest.version;

    // Check if update needed
    this.installedVersion = await this.getInstalledVersion();
    
    if (!force && this.installedVersion === bundleVersion) {
      onProgress(100, 'Already up to date');
      this.catalog = await this.loadCatalogFromDB();
      this.fontsLoaded = true;
      return false;
    }

    onProgress(5, 'Loading catalog...');

    // Fetch catalog
    const catalogRes = await fetch(`${bundlePath}/fonts.json`);
    if (!catalogRes.ok) {
      throw new Error(`Failed to load catalog: ${catalogRes.status}`);
    }
    this.catalog = await catalogRes.json();

    onProgress(10, 'Downloading fonts...');

    // Fetch bundle ZIP
    const bundleRes = await fetch(`${bundlePath}/fonts.zip`);
    if (!bundleRes.ok) {
      throw new Error(`Failed to load bundle: ${bundleRes.status}`);
    }

    const totalSize = manifest.bundle_size || parseInt(bundleRes.headers.get('content-length') || '0');
    const reader = bundleRes.body.getReader();
    const chunks = [];
    let downloadedSize = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      
      chunks.push(value);
      downloadedSize += value.length;
      
      const percent = 10 + (downloadedSize / totalSize * 60);
      const mb = (downloadedSize / 1024 / 1024).toFixed(1);
      const totalMb = (totalSize / 1024 / 1024).toFixed(1);
      onProgress(percent, `Downloading: ${mb}/${totalMb} MB`);
    }

    onProgress(70, 'Extracting fonts...');

    // Combine chunks into blob
    const zipBlob = new Blob(chunks);
    
    // Extract using JSZip (loaded dynamically if needed)
    await this.extractBundle(zipBlob, onProgress);

    onProgress(95, 'Updating database...');

    // Save catalog and version
    await this.saveCatalog(this.catalog.fonts);
    await this.setInstalledVersion(bundleVersion, manifest.version_date, manifest.bundle_sha256);
    this.installedVersion = bundleVersion;
    this.fontsLoaded = true;

    onProgress(100, `Installed ${this.catalog.fonts.length} fonts (v${bundleVersion})`);
    
    return true;
  }

  async extractBundle(zipBlob, onProgress) {
    // Dynamically load JSZip if not present
    if (typeof JSZip === 'undefined') {
      await this.loadJSZip();
    }

    const zip = await JSZip.loadAsync(zipBlob);
    const files = Object.keys(zip.files);
    const fontFiles = files.filter(f => /\.(ttf|otf|woff|woff2|ttc)$/i.test(f));
    
    let extracted = 0;
    for (const filename of fontFiles) {
      const blob = await zip.files[filename].async('blob');
      await this.saveFile(filename, blob);
      
      extracted++;
      const percent = 70 + (extracted / fontFiles.length * 25);
      onProgress(percent, `Extracting: ${filename.split('/')[0]}`);
    }
  }

  async loadJSZip() {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
      script.onload = resolve;
      script.onerror = () => reject(new Error('Failed to load JSZip'));
      document.head.appendChild(script);
    });
  }

  async loadCatalogFromDB() {
    const fonts = await this.getAllFontsFromDB();
    return { fonts };
  }

  // =========================================================================
  // Font Access
  // =========================================================================

  /**
   * Get all fonts.
   * @returns {Array} Array of font objects
   */
  getAllFonts() {
    return this.catalog?.fonts || [];
  }

  /**
   * Get a specific font by ID.
   * @param {string} fontId - Font ID (e.g., '01-inter')
   * @returns {Object|null} Font object or null
   */
  getFont(fontId) {
    return this.getAllFonts().find(f => f.id === fontId) || null;
  }

  /**
   * Get fonts with a specific tag.
   * @param {string} tag - Tag name (e.g., 'quirky', 'monospace', 'core')
   * @returns {Array} Array of matching fonts
   */
  getFontsByTag(tag) {
    return this.getAllFonts().filter(f => f.tags.includes(tag));
  }

  /**
   * Get fonts by category.
   * @param {string} category - Category (e.g., 'sans-serif', 'serif', 'monospace')
   * @returns {Array} Array of matching fonts
   */
  getFontsByCategory(category) {
    return this.getAllFonts().filter(f => f.category === category);
  }

  /**
   * Search fonts by name.
   * @param {string} query - Search query
   * @returns {Array} Array of matching fonts
   */
  searchFonts(query) {
    const q = query.toLowerCase();
    return this.getAllFonts().filter(f => f.name.toLowerCase().includes(q));
  }

  /**
   * Get a font file as a Blob URL (for use in CSS).
   * @param {string} fontId - Font ID
   * @param {string} filename - Specific file (optional, uses first available)
   * @returns {Promise<string|null>} Blob URL or null
   */
  async getFontUrl(fontId, filename = null) {
    const font = this.getFont(fontId);
    if (!font) return null;

    // Find the file - prefer WOFF2
    let file;
    if (filename) {
      file = font.files.find(f => f.filename === filename);
    } else {
      file = font.files.find(f => /\.woff2$/i.test(f.filename)) ||
             font.files.find(f => /variable/i.test(f.filename) && /\.(ttf|otf)$/i.test(f.filename)) ||
             font.files.find(f => /\.(ttf|otf)$/i.test(f.filename)) ||
             font.files.find(f => /\.woff$/i.test(f.filename));
    }

    if (!file) return null;

    const path = `${font.dir_name}/${file.filename}`;
    const blob = await this.getFile(path);
    
    if (!blob) return null;
    
    return URL.createObjectURL(blob);
  }

  /**
   * Register a font with CSS @font-face.
   * @param {string} fontId - Font ID
   * @param {string} fontFamily - CSS font-family name to use
   * @param {Object} options - Additional @font-face options
   * @returns {Promise<boolean>} Success
   */
  async registerFont(fontId, fontFamily = null, options = {}) {
    const font = this.getFont(fontId);
    if (!font) return false;

    fontFamily = fontFamily || font.name;

    // Find best font file - prefer WOFF2
    const file = font.files.find(f => /\.woff2$/i.test(f.filename)) ||
                 font.files.find(f => /variable/i.test(f.filename) && /\.(ttf|otf)$/i.test(f.filename)) ||
                 font.files.find(f => /\.(ttf|otf)$/i.test(f.filename)) ||
                 font.files.find(f => /\.woff$/i.test(f.filename));

    if (!file) return false;

    const path = `${font.dir_name}/${file.filename}`;
    const blob = await this.getFile(path);
    if (!blob) return false;

    const url = URL.createObjectURL(blob);
    
    // Determine format based on extension
    const ext = file.filename.split('.').pop().toLowerCase();
    let format;
    switch (ext) {
      case 'woff2': format = 'woff2'; break;
      case 'woff': format = 'woff'; break;
      case 'otf': format = 'opentype'; break;
      default: format = 'truetype';
    }

    const style = document.createElement('style');
    style.textContent = `
      @font-face {
        font-family: '${fontFamily}';
        src: url('${url}') format('${format}');
        font-weight: ${options.weight || 'normal'};
        font-style: ${options.style || 'normal'};
        font-display: ${options.display || 'swap'};
      }
    `;
    document.head.appendChild(style);
    
    return true;
  }

  /**
   * Get version info.
   * @returns {Object} Version info
   */
  getVersionInfo() {
    return {
      installed: this.installedVersion,
      catalog: this.catalog?.version || null,
      totalFonts: this.catalog?.fonts?.length || 0
    };
  }

  /**
   * Clear all cached fonts and data.
   * Deletes the entire IndexedDB database.
   */
  async clearCache() {
    // Close existing connection
    if (this.db) {
      this.db.close();
      this.db = null;
    }
    
    // Delete the entire database
    await new Promise((resolve, reject) => {
      const request = indexedDB.deleteDatabase(this.dbName);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
      request.onblocked = () => {
        console.warn('Database deletion blocked - closing connections');
        resolve(); // Continue anyway
      };
    });
    
    this.installedVersion = null;
    this.catalog = null;
    this.fontsLoaded = false;
  }
}

// Export for ES modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = FontLoader;
}
