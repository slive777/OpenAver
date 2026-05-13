export function stateTagAlias() {
    return {
        // ===== Tag Alias State (A3-3) =====
        tagAliasCardCollapsed: true,
        tagAliasRecords: [],            // [{primary_name, aliases, source, created_at, updated_at}]
        tagAliasRecordsLoading: false,
        tagAliasRecordsError: '',
        tagAliasInput: '',              // 單一輸入：篩選 query / 新增主名

        // ===== New Group Form =====
        newTagGroupAdding: false,

        // ===== Add Tag Alias Inline Input =====
        addingTagAlias: {},             // { [primary_name]: 'input value' }
        addingTagAliasLoading: {},      // { [primary_name]: bool }

        // ===== Tag Alias: Delete Group Modal =====
        deleteTagAliasGroupModalOpen: false,
        _deleteTagAliasGroupLoading: false,
        _pendingDeleteTagAliasGroupName: null,

        // ===== Tag Alias: Card Toggle =====
        toggleTagAliasCard() {
            this.tagAliasCardCollapsed = !this.tagAliasCardCollapsed;

            // 首次展開時載入別名列表
            if (!this.tagAliasCardCollapsed && this.tagAliasRecords.length === 0) {
                this.fetchTagAliasRecords();
            }
        },

        // ===== Tag Alias: Load Records =====
        async fetchTagAliasRecords() {
            this.tagAliasRecordsLoading = true;
            this.tagAliasRecordsError = '';

            try {
                const resp = await fetch('/api/tag-aliases');
                const result = await resp.json();

                if (result.success) {
                    this.tagAliasRecords = result.groups || [];
                } else {
                    this.tagAliasRecordsError = '載入失敗: ' + (result.error || '未知錯誤');
                }
            } catch (e) {
                this.tagAliasRecordsError = '載入失敗: ' + e.message;
            } finally {
                this.tagAliasRecordsLoading = false;
            }
        },

        // ===== Tag Alias: Filtered Records (前端 filter) =====
        filteredTagAliasRecords() {
            const q = this.tagAliasInput.trim().toLowerCase();
            if (!q) return this.tagAliasRecords;
            return this.tagAliasRecords.filter(group => {
                if (group.primary_name.toLowerCase().includes(q)) return true;
                return (group.aliases || []).some(a => a.toLowerCase().includes(q));
            });
        },

        // ===== Tag Alias: Create Group =====
        async addTagAliasGroup() {
            const name = this.tagAliasInput.trim();
            if (!name) return;

            this.newTagGroupAdding = true;
            try {
                const resp = await fetch('/api/tag-aliases', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ primary_name: name })
                });
                const result = await resp.json();

                if (result.success) {
                    this.showToast('已新增 Tag 別名組：' + name, 'success');
                    this.tagAliasInput = '';
                    await this.fetchTagAliasRecords();
                } else {
                    this.showToast('新增失敗: ' + (result.error || '未知錯誤'), 'error');
                }
            } catch (e) {
                this.showToast('新增失敗: ' + e.message, 'error');
            } finally {
                this.newTagGroupAdding = false;
            }
        },

        // ===== Tag Alias: Delete Group =====
        // thin wrapper → opens modal（不用 native confirm）
        deleteTagAliasGroup(name) {
            this.openDeleteTagAliasGroupModal(name);
        },

        // ===== Tag Alias: Delete Group Modal — Open =====
        openDeleteTagAliasGroupModal(name) {
            this._pendingDeleteTagAliasGroupName = name;
            this.deleteTagAliasGroupModalOpen = true;
        },

        // ===== Tag Alias: Delete Group Modal — Cancel =====
        cancelDeleteTagAliasGroupModal() {
            this.deleteTagAliasGroupModalOpen = false;
            this._pendingDeleteTagAliasGroupName = null;
        },

        // ===== Tag Alias: Delete Group Modal — Confirm =====
        async confirmDeleteTagAliasGroup() {
            const name = this._pendingDeleteTagAliasGroupName;
            if (!name) {
                this.deleteTagAliasGroupModalOpen = false;
                this._pendingDeleteTagAliasGroupName = null;
                return;
            }
            this._deleteTagAliasGroupLoading = true;
            try {
                const resp = await fetch(`/api/tag-aliases/${encodeURIComponent(name)}`, {
                    method: 'DELETE'
                });
                const result = await resp.json();

                if (result.success) {
                    this.showToast('已刪除：' + name, 'success');
                    await this.fetchTagAliasRecords();
                } else {
                    this.showToast('刪除失敗: ' + (result.error || '未知錯誤'), 'error');
                }
            } catch (e) {
                this.showToast('刪除失敗: ' + e.message, 'error');
            } finally {
                this._deleteTagAliasGroupLoading = false;
                this.deleteTagAliasGroupModalOpen = false;
                this._pendingDeleteTagAliasGroupName = null;
            }
        },

        // ===== Tag Alias: Show Add Alias Inline Input =====
        showAddTagAliasInput(primary, show = true) {
            if (show) {
                this.addingTagAlias = { ...this.addingTagAlias, [primary]: '' };
            } else {
                const updated = { ...this.addingTagAlias };
                delete updated[primary];
                this.addingTagAlias = updated;
            }
        },

        // ===== Tag Alias: Add Alias to Group =====
        async submitAddTagAlias(primary) {
            const alias = (this.addingTagAlias[primary] || '').trim();
            if (!alias) return;

            this.addingTagAliasLoading = { ...this.addingTagAliasLoading, [primary]: true };
            try {
                const resp = await fetch(`/api/tag-aliases/${encodeURIComponent(primary)}/alias`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alias })
                });
                const result = await resp.json();

                if (result.success) {
                    // 清除 inline input
                    const updated = { ...this.addingTagAlias };
                    delete updated[primary];
                    this.addingTagAlias = updated;
                    await this.fetchTagAliasRecords();
                } else {
                    this.showToast(result.error || '新增別名失敗', 'error');
                }
            } catch (e) {
                this.showToast('新增別名失敗: ' + e.message, 'error');
            } finally {
                const loading = { ...this.addingTagAliasLoading };
                delete loading[primary];
                this.addingTagAliasLoading = loading;
            }
        },

        // ===== Tag Alias: Remove Alias from Group =====
        async removeTagAlias(primary, alias) {
            try {
                const resp = await fetch(
                    `/api/tag-aliases/${encodeURIComponent(primary)}/alias/${encodeURIComponent(alias)}`,
                    { method: 'DELETE' }
                );
                const result = await resp.json();

                if (result.success) {
                    await this.fetchTagAliasRecords();
                } else {
                    this.showToast('移除失敗: ' + (result.error || '未知錯誤'), 'error');
                }
            } catch (e) {
                this.showToast('移除失敗: ' + e.message, 'error');
            }
        },
    };
}
