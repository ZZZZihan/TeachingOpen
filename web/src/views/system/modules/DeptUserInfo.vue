<template>
  <a-card class="member-workspace" :bordered="false" :bodyStyle="{ padding: 0 }">
    <div class="member-workspace-heading">
      <div>
        <h3>班级成员</h3>
        <p>查看成员并维护班级关联。</p>
      </div>
      <span class="member-workspace-context">{{ currentDept.departName || '请先选择班级' }}</span>
    </div>

    <div class="member-search-panel">
      <a-form layout="vertical" class="member-search-form">
        <a-form-item label="账号" :htmlFor="'member-username-' + _uid">
          <a-input :id="'member-username-' + _uid" placeholder="请输入账号" v-model="queryParam.username"></a-input>
        </a-form-item>
        <a-form-item label="姓名" :htmlFor="'member-realname-' + _uid">
          <a-input :id="'member-realname-' + _uid" placeholder="请输入姓名" v-model="queryParam.realname"></a-input>
        </a-form-item>
        <div class="member-search-actions">
          <a-button type="primary" @click="searchQuery" icon="search">查询</a-button>
          <a-button @click="searchReset" icon="reload">重置</a-button>
        </div>
      </a-form>
    </div>

    <div class="member-toolbar" role="group" aria-label="班级成员操作">
      <div class="member-toolbar-group">
        <a-button @click="handleAddUserDepart" :disabled="operationsDisabled" type="primary" icon="plus">添加已有用户</a-button>
        <a-button @click="handleAdd" :disabled="operationsDisabled" icon="user-add">新建用户</a-button>
        <a-upload
          name="file"
          :showUploadList="false"
          :multiple="false"
          :headers="tokenHeader"
          :action="url.importStudentUrl"
          :disabled="operationsDisabled"
          :beforeUpload="beforeImportUpload"
          :customRequest="handleImportRequest"
          @change="handleImportExcel"
        >
          <a-button :disabled="operationsDisabled" icon="import">导入学生</a-button>
        </a-upload>
      </div>
      <div class="member-toolbar-group">
        <a-dropdown v-if="selectedRowKeys.length > 0" :trigger="['click']">
          <a-menu slot="overlay">
            <a-menu-item key="1" @click="batchDel">
              <a-icon type="delete"/>
              取消关联
            </a-menu-item>
          </a-menu>
          <a-button :disabled="operationsDisabled">批量操作 <a-icon type="down"/></a-button>
        </a-dropdown>
        <a-button class="member-danger-action" @click="handleRemoveAll" :disabled="operationsDisabled" icon="delete">清空班级</a-button>
      </div>
    </div>

    <a-alert v-if="listError || actionError" class="member-feedback" type="error" show-icon>
      <span slot="message">{{ listError || actionError }} <a href="#" @click.prevent="loadData()">刷新重试</a></span>
    </a-alert>
    <p v-if="importReport" class="member-import-report">{{ importReport.message }} <a v-if="importReport.url" :href="importReport.url" target="_blank" rel="noopener noreferrer">下载导入明细</a></p>
    <div class="member-table-summary">
      <div class="member-selection-status" role="status" aria-live="polite">
        <span>已选择 <strong>{{ selectedRowKeys.length }}</strong> 位成员</span>
        <a-button type="link" size="small" @click="onClearSelected" :disabled="selectedRowKeys.length === 0">清空选择</a-button>
      </div>
      <p class="member-scroll-hint">表格可横向滚动，聚焦后用 ← → 查看。</p>
    </div>

    <div
      class="member-table-region"
      role="region"
      tabindex="0"
      aria-label="班级成员表格，左右方向键横向滚动"
      @keydown.left.self.prevent="$event.currentTarget.querySelector('.ant-table-body').scrollLeft -= 120"
      @keydown.right.self.prevent="$event.currentTarget.querySelector('.ant-table-body').scrollLeft += 120">
      <a-table
        ref="table"
        size="middle"
        bordered
        rowKey="id"
        :columns="columns"
        :dataSource="dataSource"
        :pagination="ipagination"
        :scroll="{ x: 920 }"
        :loading="loading || mutationLoading || importLoading"
        :rowSelection="{selectedRowKeys: selectedRowKeys, onChange: onSelectChange, columnWidth: 64}"
        @change="handleTableChange">
        <span slot="action" slot-scope="text, record" class="member-row-actions">
          <a-button type="link" size="small" :disabled="operationsDisabled" @click="handleEdit(record)">编辑</a-button>
          <a-dropdown :trigger="['click']">
            <a-button type="link" size="small" :disabled="operationsDisabled">更多 <a-icon type="down"/></a-button>
            <a-menu slot="overlay">
              <a-menu-item>
                <a href="#" @click.prevent="handleDeptRole(record)">分配部门角色</a>
              </a-menu-item>
              <a-menu-item>
                <a href="#" @click.prevent="handleDetail(record)">用户详情</a>
              </a-menu-item>
              <a-menu-item>
                <a :disabled="operationsDisabled" href="#" @click.prevent="confirmDelete(record)">取消关联</a>
              </a-menu-item>
            </a-menu>
          </a-dropdown>
        </span>
      </a-table>
    </div>

    <user-modal ref="modalForm" @ok="modalFormOk"></user-modal>
    <Select-User-Modal ref="selectUserModal" @selectFinished="selectOK"></Select-User-Modal>
    <dept-role-user-modal ref="deptRoleUser"></dept-role-user-modal>
  </a-card>
</template>

<script>
  import {JeecgListMixin} from '@/mixins/JeecgListMixin'
  import {getAction, postAction, deleteAction} from '@/api/manage'
  import SelectUserModal from './SelectUserModal'
  import UserModal from './UserModal'
  import uploadRequest from 'ant-design-vue/es/vc-upload/src/request'
  import DeptRoleUserModal from './DeptRoleUserModal'

  export default {
    name: "DeptUserInfo",
    mixins: [JeecgListMixin],
    components: {
      DeptRoleUserModal,
      SelectUserModal,
      UserModal
    },
    data() {
      return {
        description: '用户信息',
        currentDeptId: '',
        currentDept: {},
        contextVersion: 0,
        listRequestId: 0,
        writeRequestId: 0,
        selectionVersion: 0,
        mutationLoading: false,
        importLoading: false,
        importContexts: {},
        importReport: null,
        listError: '',
        actionError: '',
        membershipPrompt: null,
        // 表头
        columns: [{
            title: '用户账号',
            align: "center",
            width: 150,
            dataIndex: 'username'
          },
          {
            title: '用户名称',
            align: "center",
            width: 140,
            dataIndex: 'realname'
          },
          {
            title: '部门',
            align: "center",
            width: 180,
            dataIndex: 'orgCode'
          },
          {
            title: '性别',
            align: "center",
            width: 76,
            dataIndex: 'sex_dictText'
          },
          {
            title: '电话',
            align: "center",
            width: 150,
            dataIndex: 'phone'
          },
          {
            title: '操作',
            dataIndex: 'action',
            scopedSlots: {customRender: 'action'},
            align: "center",
            width: 160
          }],
        url: {
          list: "/sys/user/departUserList",
          edit: "/sys/user/editSysDepartWithUser",
          delete: "/sys/user/deleteUserInDepart",
          deleteBatch: "/sys/user/deleteUserInDepartBatch",
          removeAll: '/sys/sysDepart/removeAll',
          importStudentUrl: '/api/sys/user/importStudent',
        }
      }
    },
    created() {
    },

    computed: {
      operationsDisabled() {
        return !this.currentDeptId || this.loading || this.mutationLoading || this.importLoading || !!this.listError
      }
    },
    beforeDestroy() { this.clearList() },
    methods: {
      searchReset() { this.queryParam = {}; return this.loadData(1) },
      loadData(arg) {
        if (!this.currentDeptId) return
        if (arg === 1) this.ipagination.current = 1
        const context = this.captureContext()
        const requestId = ++this.listRequestId
        const params = Object.assign({}, this.getQueryParams(), { depId: context.deptId })
        this.loading = true
        this.listError = ''
        this.actionError = ''
        this.dataSource = []
        this.ipagination.total = 0
        this.onClearSelected()
        const isCurrent = () => this.isCurrentContext(context) && requestId === this.listRequestId
        return getAction(this.url.list, params).then(res => {
          if (!isCurrent()) return
          if (res && res.success === true && res.result && this.isValidRecords(res.result.records)) {
            this.dataSource = res.result.records
            this.ipagination.total = Number(res.result.total) || 0
          } else this.listError = '成员列表加载失败，请重试。'
        }).catch(() => {
          if (isCurrent()) this.listError = '成员列表加载失败，请重试。'
        }).finally(() => { if (isCurrent()) this.loading = false })
      },
      captureContext() { return { deptId: this.currentDeptId, contextVersion: this.contextVersion } },
      modalContext() {
        const context = this.captureContext()
        context.isCurrent = () => this.isCurrentContext(context)
        return context
      },
      isCurrentContext(context) {
        return !!context && !!context.deptId && context.deptId === this.currentDeptId && context.contextVersion === this.contextVersion
      },
      isValidRecords(records) {
        return Array.isArray(records) && records.every(row => row && typeof row === 'object' && !Array.isArray(row) && (typeof row.id === 'string' || typeof row.id === 'number') && row.id !== '')
      },
      isCurrentUser(record) { return !!record && this.dataSource.indexOf(record) !== -1 },
      onSelectChange(keys, rows) {
        if (this.operationsDisabled || !keys.every(id => this.dataSource.some(row => row.id === id))) return
        this.selectedRowKeys = keys.slice()
        this.selectionRows = rows.slice()
        this.selectionVersion++
      },
      onClearSelected() { this.selectedRowKeys = []; this.selectionRows = []; this.selectionVersion++ },
      open(record) { this.resetContext(record); return this.loadData(1) },
      clearList() { this.resetContext() },
      resetContext(record) {
        this.contextVersion++
        this.listRequestId++
        this.currentDept = Object.assign({}, record || {})
        this.currentDeptId = record && record.id ? record.id : ''
        this.url.importStudentUrl = '/api/sys/user/importStudent?departIds=' + encodeURIComponent(this.currentDeptId)
        this.queryParam = {}
        this.dataSource = []
        this.onClearSelected()
        this.ipagination.current = 1
        this.ipagination.total = 0
        this.loading = false
        this.mutationLoading = false
        this.importLoading = false
        this.importReport = null
        this.listError = ''
        this.actionError = ''
        this.membershipPrompt = null
        if (this.$refs.selectUserModal) this.$refs.selectUserModal.handleCancel()
        if (this.$refs.modalForm) this.$refs.modalForm.close()
        if (this.$refs.deptRoleUser) this.$refs.deptRoleUser.close()
      },
      hasSelectDept() {
        if (!this.currentDeptId) { this.$message.error('请选择一个部门!'); return false }
        return true
      },
      batchDel() {
        if (this.operationsDisabled || this.membershipPrompt) return
        if (!this.selectedRowKeys.length) { this.$message.warning('请选择成员！'); return }
        const snapshot = Object.assign(this.captureContext(), { kind: 'batch', userIds: this.selectedRowKeys.slice(), selectionVersion: this.selectionVersion })
        this.openMembershipPrompt(snapshot, '确认取消关联', '是否取消选中成员与该班级的关联?')
      },
      handleRemoveAll() {
        if (this.operationsDisabled || this.membershipPrompt) return
        const snapshot = Object.assign(this.captureContext(), { kind: 'all' })
        this.openMembershipPrompt(snapshot, '确认清空班级', '清空班级内所有成员，此操作不会删除用户账号。')
      },
      confirmDelete(record) {
        if (this.operationsDisabled || this.membershipPrompt || !this.isCurrentUser(record)) return
        const snapshot = Object.assign(this.captureContext(), { kind: 'one', userIds: [record.id], record })
        this.openMembershipPrompt(snapshot, '确认取消关联', '是否取消此成员与该班级的关联?')
      },
      openMembershipPrompt(snapshot, title, content) {
        this.membershipPrompt = snapshot
        this.$confirm({ title, content: `班级“${this.currentDept.departName || snapshot.deptId}”：${content}`,
          onOk: () => {
            if (this.membershipPrompt !== snapshot) return
            this.membershipPrompt = null
            return this.applyMembershipRemoval(snapshot)
          },
          onCancel: () => { if (this.membershipPrompt === snapshot) this.membershipPrompt = null }
        })
      },
      handleDelete(id, snapshot) {
        if (!snapshot || snapshot.kind !== 'one' || snapshot.userIds[0] !== id) return
        return this.applyMembershipRemoval(snapshot)
      },
      applyMembershipRemoval(snapshot) {
        const ids = snapshot.userIds || []
        const sameSelection = snapshot.kind !== 'batch' || (snapshot.selectionVersion === this.selectionVersion && ids.length === this.selectedRowKeys.length && ids.every(id => this.selectedRowKeys.indexOf(id) !== -1))
        const validUsers = snapshot.kind === 'all' || (ids.length > 0 && ids.every(id => this.dataSource.some(row => row.id === id)))
        if (!this.isCurrentContext(snapshot) || !sameSelection || !validUsers || (snapshot.kind === 'one' && !this.isCurrentUser(snapshot.record))) {
          this.$message.warning('班级或成员选择已变化，请重新确认。')
          return
        }
        if (this.operationsDisabled) return
        if (snapshot.kind === 'all') return this.runMembershipWrite(snapshot, this.url.removeAll, { id: snapshot.deptId }, 'get', '班级已清空')
        if (snapshot.kind === 'batch') return this.runMembershipWrite(snapshot, this.url.deleteBatch, { depId: snapshot.deptId, userIds: ids.join(',') + ',' }, 'delete', '成员关联已取消')
        return this.runMembershipWrite(snapshot, this.url.delete, { depId: snapshot.deptId, userId: ids[0] }, 'delete', '成员关联已取消')
      },
      runMembershipWrite(context, url, params, method, message) {
        const requestId = ++this.writeRequestId
        this.mutationLoading = true
        this.actionError = ''
        const isCurrent = () => this.isCurrentContext(context) && requestId === this.writeRequestId
        const request = method === 'delete' ? deleteAction : (method === 'get' ? getAction : postAction)
        return request(url, params).then(res => {
          if (!isCurrent()) return
          if (res && res.success === true) {
            this.$message.success(message)
            return this.loadData()
          }
          this.actionError = '操作未成功，请重试。'
        }).catch(() => {
          if (isCurrent()) this.actionError = '未能确认操作结果，请刷新成员列表核对后重试。'
        }).finally(() => { if (isCurrent()) this.mutationLoading = false })
      },
      handleAddUserDepart() {
        if (this.operationsDisabled) return
        this.$refs.selectUserModal.show(this.captureContext())
      },
      selectOK(data) {
        if (!this.isCurrentContext(data)) { this.$message.warning('班级已变化，请重新选择成员。'); return }
        if (this.operationsDisabled || !Array.isArray(data.userIdList) || !data.userIdList.length) return
        return this.runMembershipWrite(this.captureContext(), this.url.edit, { depId: data.deptId, userIdList: data.userIdList.slice() }, 'post', '成员已加入班级')
      },
      handleEdit(record) {
        if (this.operationsDisabled || !this.isCurrentUser(record)) return
        const modal = this.$refs.modalForm
        modal.title = '编辑'; modal.departDisabled = true; modal.disableSubmit = false
        modal.edit(record, this.modalContext())
      },
      handleDetail(record) {
        if (this.operationsDisabled || !this.isCurrentUser(record)) return
        const modal = this.$refs.modalForm
        modal.title = '用户详情'; modal.departDisabled = true; modal.disableSubmit = true
        modal.edit(record, this.modalContext())
      },
      handleAdd() {
        if (this.operationsDisabled) return
        const modal = this.$refs.modalForm
        modal.departDisabled = true; modal.disableSubmit = false
        modal.userDepartModel = { userId: '', departIdList: [this.currentDeptId] }
        modal.add(this.modalContext()); modal.title = '新增'
      },
      modalFormOk(context) { if (this.isCurrentContext(context)) return this.loadData() },
      handleDeptRole(record) {
        if (this.operationsDisabled || !this.isCurrentUser(record)) return
        this.$refs.deptRoleUser.add(record, this.currentDeptId, this.modalContext())
        this.$refs.deptRoleUser.title = '部门角色分配'
      },
      beforeImportUpload(file) {
        if (this.operationsDisabled || this.membershipPrompt || !file || !file.uid) return false
        this.$set(this.importContexts, file.uid, Object.assign(this.captureContext(), { url: this.url.importStudentUrl, sent: false }))
        this.importLoading = true
        this.actionError = ''
        this.importReport = null
        return true
      },
      handleImportRequest(options) {
        const file = options.file || {}
        const context = this.importContexts[file.uid]
        if (!this.isCurrentContext(context)) {
          if (context) this.$delete(this.importContexts, file.uid)
          options.onError(new Error('班级已变化，请重新选择导入文件。'))
          return { abort() {} }
        }
        context.sent = true
        return uploadRequest(Object.assign({}, options, { action: context.url }))
      },
      handleImportExcel(info) {
        if (!info || !info.file) return
        const file = info.file
        const context = this.importContexts[file.uid]
        if (!context) return
        const current = this.isCurrentContext(context)
        if (file.status === 'uploading') { if (current) this.importLoading = true; return }
        if (['done', 'error', 'removed'].indexOf(file.status) === -1) return
        this.$delete(this.importContexts, file.uid)
        if (!current) return
        this.importLoading = false
        if (file.status === 'removed') return
        if (file.status === 'error' || !file.response || file.response.success !== true) {
          this.actionError = '导入未能确认完成，请核对文件、网络和成员列表后重试。'
          return
        }
        if (file.response.code === 201) {
          const result = file.response.result || {}
          let url = ''
          try {
            const candidate = new URL((window._CONFIG['domianURL'] || '') + (result.fileUrl || ''), window.location.origin)
            if (result.fileUrl && ['http:', 'https:'].indexOf(candidate.protocol) !== -1 && !candidate.username && !candidate.password) url = candidate.href
          } catch (error) {}
          this.importReport = { message: '导入已处理，请核对明细中的失败记录。', url }
        } else this.$message.success('成员已导入')
        return this.loadData()
      }
    }
  }
</script>
<style scoped>
.member-workspace {
  width: 100%;
  min-width: 0;
  color: #29222b;
}
.member-workspace-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px 24px;
  margin-bottom: 20px;
}
.member-workspace-heading h3 {
  margin: 0 0 6px;
  color: #29222b;
  font-size: 20px;
  font-weight: 600;
}
.member-workspace-heading p {
  margin: 0;
  color: #6e6570;
  line-height: 1.6;
}
.member-workspace-context {
  max-width: 100%;
  padding: 5px 10px;
  border: 1px solid #e4dce3;
  border-radius: 4px;
  color: #74256a;
  background: #fcfafc;
  overflow-wrap: anywhere;
}
.member-search-panel {
  padding: 16px;
  border: 1px solid #e9e2e8;
  border-radius: 6px;
  background: #fcfafc;
}
.member-search-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr));
  align-items: end;
  gap: 12px 16px;
  min-width: 0;
}
.member-search-form /deep/ .ant-form-item {
  min-width: 0;
  margin: 0;
}
.member-search-form /deep/ .ant-form-item-label {
  padding-bottom: 6px;
  line-height: 1.4;
}
.member-search-form /deep/ .ant-form-item-label label {
  color: #534757;
  font-size: 13px;
}
.member-search-form /deep/ .ant-input {
  height: 36px;
}
.member-search-actions,
.member-toolbar,
.member-toolbar-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.member-search-actions .ant-btn {
  flex: 1 1 auto;
}
.member-toolbar {
  justify-content: space-between;
  gap: 12px;
  padding: 18px 0;
  border-bottom: 1px solid #eee8ed;
}
.member-workspace /deep/ .ant-btn {
  margin: 0;
}
.member-search-actions .ant-btn,
.member-toolbar .ant-btn {
  height: 36px;
}
.member-workspace /deep/ .ant-btn-primary:not([disabled]) {
  background: #74256a;
  border-color: #74256a;
}
.member-workspace /deep/ .ant-btn-primary:not([disabled]):hover {
  background: #592052;
  border-color: #592052;
}
.member-workspace /deep/ .ant-btn-link:not([disabled]),
.member-workspace a {
  color: #74256a;
}
.member-danger-action:not([disabled]) {
  color: #a63b41;
  border-color: #e2c6c8;
}
.member-danger-action:not([disabled]):hover {
  color: #8c272d;
  border-color: #a63b41;
}
.member-feedback,
.member-import-report {
  margin-top: 16px;
  overflow-wrap: anywhere;
}
.member-table-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin: 16px 0 12px;
}
.member-selection-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  color: #534757;
}
.member-selection-status strong {
  color: #74256a;
}
.member-scroll-hint {
  margin: 0;
  color: #6e6570;
  font-size: 12px;
  line-height: 1.6;
}
.member-table-region {
  width: 100%;
  min-width: 0;
  border-radius: 4px;
}
.member-table-region:focus-visible {
  outline: 2px solid #74256a;
  outline-offset: 3px;
}
.member-table-region /deep/ .ant-table-wrapper,
.member-table-region /deep/ .ant-spin-nested-loading,
.member-table-region /deep/ .ant-spin-container,
.member-table-region /deep/ .ant-table,
.member-table-region /deep/ .ant-table-content,
.member-table-region /deep/ .ant-table-scroll {
  min-width: 0;
  max-width: 100%;
}
.member-table-region /deep/ .ant-table-wrapper .ant-table .ant-table-body {
  min-width: 0;
  max-width: 100%;
}
.member-table-region /deep/ .ant-table-thead > tr > th {
  color: #534757;
  background: #f8f5f8;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.member-table-region /deep/ .ant-table-tbody > tr > td {
  overflow-wrap: anywhere;
}
.member-row-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.member-table-region /deep/ .ant-table-pagination.ant-pagination {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  float: none;
  width: 100%;
  max-width: 100%;
  margin: 16px 0 0;
}
.member-table-region /deep/ .ant-pagination > li {
  margin: 0;
}
.member-table-region /deep/ .ant-pagination-options {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
}
.member-table-region /deep/ .ant-pagination-options-size-changer.ant-select {
  margin: 0;
}
</style>
