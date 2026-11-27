import { buildActressIndex } from '@/shared/actress-lookup.js';
import { computeActorAgesMap } from '@/shared/actress-release-age.js';
import { actorFavsOf } from '@/showcase/lbx-logic.js';

function buildNameToGroup(groups) {
    const map = {};
    for (const group of groups) {
        const names = [group.primary_name, ...(group.aliases || [])];
        for (const name of names) map[name.toLowerCase()] = names;
    }
    return map;
}

async function fetchFavs() {
    try {
        const [actressResp, aliasResp] = await Promise.all([fetch('/api/actresses'), fetch('/api/actress-aliases')]);
        if (!actressResp.ok || !aliasResp.ok) return null;
        const [data, aliases] = await Promise.all([actressResp.json(), aliasResp.json()]);
        if (!data.success) return null;
        return { actresses: data.actresses || [], nameToGroup: buildNameToGroup(aliases.groups || []) };
    } catch {
        return null;
    }
}

export function searchStateLbxFavs() {
    let _actresses = [], _nameToGroup = {}, _index = null;
    let _lbxFavsStarted = false, _lbxFavsGen = 0;
    let _lbxFavsApplied = 0;
    async function run(self) {
        const gen = ++_lbxFavsGen;
        const data = await fetchFavs();
        if (gen <= _lbxFavsApplied) return;
        if (!data) return;
        _actresses = data.actresses;
        _nameToGroup = data.nameToGroup;
        _index = buildActressIndex(_actresses, _nameToGroup);
        _lbxFavsApplied = gen;
        self.lbxFavsRev++;
        self._refreshLbActorAges();
    }
    return {
        _lbActorFavs: {}, _lbActorAges: {}, lbxFavsRev: 0,
        _refreshLbActorAges() {
            const video = this.lbxView();
            this._lbActorAges = { ...computeActorAgesMap(video, _actresses, _nameToGroup) };
            this._lbActorFavs = actorFavsOf(video, _index);
        },
        lbxActorEntity(name) {
            void this.lbxFavsRev;
            return _index ? _index.lookup(name) : null;
        },
        actressWorkCount() { return null; },
        lbxFavsLoad() {
            if (_lbxFavsStarted) return;
            _lbxFavsStarted = true;
            return run(this);
        },
        lbxFavsReload() {
            _lbxFavsStarted = true;
            return run(this);
        },
    };
}
