import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
window.t = (k) => k;

register(
  new URL('../../search/__tests__/alias-loader.mjs', import.meta.url),
  import.meta.url,
);

const { stateScan } = await import('../state-scan.js');

function versionA() {
  return {
    translate: {
      openai: { base_url: 'http://old/v1', model: 'm' },
    },
    gallery: {
      workers: 2,
      directories: [{ path: '/a' }],
    },
  };
}

function versionB() {
  return {
    translate: {
      openai: { base_url: 'http://new/v1', model: 'm' },
      openai_custom: {
        oc0123abcd: { name: 'X', base_url: 'http://stub/v1', model: 'm', api_key: '' },
      },
    },
    gallery: {
      workers: 2,
      output_dir: '/out',
      directories: [{ path: '/a' }],
    },
  };
}

function makeHarness() {
  const toastCalls = [];
  const fakeThis = Object.assign({}, stateScan(), {
    showToast(message, type) {
      toastCalls.push({ message, type });
    },
  });
  return { fakeThis, toastCalls };
}

test('save_config_uses_fresh_snapshot', async () => {
  const { fakeThis, toastCalls } = makeHarness();
  let mode = 'A';
  const puts = [];
  const events = [];
  const origFetch = globalThis.fetch;
  const origDispatch = window.dispatchEvent;
  window.dispatchEvent = (e) => { events.push(e.type); return true; };
  globalThis.fetch = async (url, opts) => {
    if (!opts || !opts.method) {
      const data = mode === 'A' ? versionA() : versionB();
      return {
        json: async () => ({
          success: true,
          data: structuredClone(data),
          resolved: { gallery_output_path: '/resolved' },
          cf_window_proxy_restart_needed: false,
        }),
      };
    }
    if (opts.method === 'PUT') {
      puts.push(JSON.parse(opts.body));
      return { json: async () => ({ success: true }) };
    }
    throw new Error('unexpected fetch');
  };
  try {
    await stateScan().loadConfig.call(fakeThis);
    fakeThis.directories.push({ path: '/newdir' });
    mode = 'B';
    const ret = await stateScan().saveConfig.call(fakeThis);
    const expectedNewDirs = [...versionB().gallery.directories, { path: '/newdir' }];
    const expectedBody = structuredClone(versionB());
    expectedBody.gallery.directories = expectedNewDirs;

    assert.equal(puts.length, 1);
    const { directories: _d, ...putRest } = puts[0].gallery;
    const { directories: _e, ...expRest } = expectedBody.gallery;
    assert.deepEqual({ ...puts[0], gallery: putRest }, { ...expectedBody, gallery: expRest });
    assert.ok(!('resolved' in puts[0]));
    assert.ok(!('cf_window_proxy_restart_needed' in puts[0]));
    assert.deepEqual(puts[0].gallery.directories, expectedNewDirs);
    assert.equal(ret, true);
    assert.equal(fakeThis.configDirty, false);
    assert.equal(fakeThis.folderSnapshot, JSON.stringify(fakeThis.directories));
    assert.deepEqual(fakeThis.config, puts[0]);
    assert.equal(toastCalls.length, 1);
    assert.equal(toastCalls[0].message, 'scanner.toast.config_saved');
    assert.equal(toastCalls[0].type, 'success');
    assert.deepEqual(events, ['media-probe-refresh']);
  } finally {
    globalThis.fetch = origFetch;
    window.dispatchEvent = origDispatch;
  }
});

test('save_config_get_failure_sends_no_put', async () => {
  const { fakeThis, toastCalls } = makeHarness();
  let failGet = false;
  let putCount = 0;
  const origFetch = globalThis.fetch;
  const origDispatch = window.dispatchEvent;
  window.dispatchEvent = (e) => true;
  globalThis.fetch = async (url, opts) => {
    if (!opts || !opts.method) {
      if (failGet) {
        return { json: async () => ({ success: false, error: 'boom' }) };
      }
      return {
        json: async () => ({
          success: true,
          data: structuredClone(versionA()),
          resolved: {},
          cf_window_proxy_restart_needed: false,
        }),
      };
    }
    if (opts.method === 'PUT') {
      putCount++;
      return { json: async () => ({ success: true }) };
    }
    throw new Error('unexpected fetch');
  };
  try {
    await stateScan().loadConfig.call(fakeThis);
    fakeThis.directories.push({ path: '/dirty' });
    fakeThis.configDirty = true;
    const snapBefore = fakeThis.folderSnapshot;
    const configBefore = structuredClone(fakeThis.config);
    failGet = true;
    const ret = await stateScan().saveConfig.call(fakeThis);

    assert.equal(putCount, 0);
    assert.equal(ret, false);
    assert.equal(toastCalls.length, 1);
    assert.equal(toastCalls[0].message, 'scanner.toast.save_failed');
    assert.equal(toastCalls[0].type, 'error');
    assert.equal(fakeThis.configDirty, true);
    assert.equal(fakeThis.folderSnapshot, snapBefore);
    assert.deepEqual(fakeThis.config, configBefore);
  } finally {
    globalThis.fetch = origFetch;
    window.dispatchEvent = origDispatch;
  }
});
