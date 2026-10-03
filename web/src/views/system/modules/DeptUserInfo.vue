<template>
  <a-card :bordered="false">
    <!-- 查询区域 -->
    <div class="table-page-search-wrapper">
      <!-- 搜索区域 -->
      <a-form layout="inline">
        <a-row :gutter="10">
          <a-col :md="8" :sm="8">
            <a-form-item label="账号" style="margin-left:8px">
              <a-input placeholder="请输入账号" v-model="queryParam.username"></a-input>
            </a-form-item>
          </a-col>
          <a-col :md="8" :sm="8">
            <a-form-item label="姓名" :labelCol="{span: 5}" :wrapperCol="{span: 18, offset: 1}">
              <a-input placeholder="请输入姓名" v-model="queryParam.realname"></a-input>
            </a-form-item>
          </a-col>
          <span style="float: left;overflow: hidden;" class="table-page-search-submitButtons">
            <a-col :md="6" :sm="24">
             <a-button type="primary" @click="searchQuery" icon="search" style="margin-left: 18px">查询</a-button>
              <a-button type="primary" @click="searchReset" icon="reload" style="margin-left: 8px">重置</a-button>
            </a-col>
          </span>
        </a-row>
      </a-form>
    </div>
    <!-- 操作按钮区域 -->
    <div class="table-operator" :md="24" :sm="24" style="margin-top: -15px">
      <!--<a-button @click="handleEdit" type="primary" icon="edit" style="margin-top: 16px">用户编辑</a-button>-->
      <a-button @click="handleAddUserDepart" :disabled="operationsDisabled" type="primary" icon="plus">添加已有用户</a-button>
      <a-button @click="handleAdd" :disabled="operationsDisabled" type="primary" icon="plus" style="margin-top: 16px">新建用户</a-button>
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
        <a-button :disabled="operationsDisabled" type="primary" icon="import">导入学生</a-button>
      </a-upload>
      <a-button @click="handleRemoveAll" :disabled="operationsDisabled" type="default" icon="delete" style="margin-top: 16px">清空班级</a-button>
      <a-dropdown v-if="selectedRowKeys.length > 0">
        <a-menu slot="overlay">
          <a-menu-item key="1" @click="batchDel">
            <a-icon type="delete"/>
            取消关联
          </a-menu-item>
        </a-menu>
        <a-button :disabled="operationsDisabled" style="margin-left: 8px"> 批量操作
          <a-icon type="down"/>
        </a-button>
      </a-dropdown>
    </div>

    <!-- table区域-begin -->
    <div>
      <a-alert v-if="listError || actionError" type="error" show-icon style="margin-bottom: 16px">
        <span slot="message">{{ listError || actionError }} <a @click="loadData()">刷新重试</a></span>
      </a-alert>
      <p v-if="importReport">{{ importReport.message }} <a v-if="importReport.url" :href="importReport.url" target="_blank" rel="noopener noreferrer">下载导入明细</a></p>
      <div class="ant-alert ant-alert-info" style="margin-bottom: 16px;">
        <i class="anticon anticon-info-circle ant-alert-icon"></i> 已选择 <a style="font-weight: 600">{{
        selectedRowKeys.length }}</a>项
        <a style="margin-left: 24px" @click="onClearSelected">清空</a>
      </div>

      <a-table
        ref="table"
        size="middle"
        bordered
        rowKey="id"
        :columns="columns"
        :dataSource="dataSource"
        :pagination="ipagination"
        :loading="loading || mutationLoading || importLoading"
        :rowSelection="{selectedRowKeys: selectedRowKeys, onChange: onSelectChange}"
        @change="handleTableChange">



        <span slot="action" slot-scope="text, record">
          <a :disabled="operationsDisabled" @click="handleEdit(record)">编辑</a>

          <a-divider type="vertical"/>

          <a-dropdown>
            <a class="ant-dropdown-link">
              更多 <a-icon type="down"/>
            </a>
            <a-menu slot="overlay">
                <a-menu-item>
                <a href="javascript:;" @click="handleDeptRole(record)">分配部门角色</a>
              </a-menu-item>

              <a-menu-item>
                <a href="javascript:;" @click="handleDetail(record)">用户详情</a>
              </a-menu-item>

              <a-menu-item>
                <a :disabled="operationsDisabled" @click="confirmDelete(record)">取消关联</a>
              </a-menu-item>
            </a-menu>
          </a-dropdown>
        </span>


      </a-table>
    </div>
    <!-- table区域-end -->

    <!-- 表单区域 -->
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
            dataIndex: 'username'
          },
          {
            title: '用户名称',
            align: "center",
            dataIndex: 'realname'
          },
          {
            title: '部门',
            align: "center",
            dataIndex: 'orgCode'
          },
          {
            title: '性别',
            align: "center",
            dataIndex: 'sex_dictText'
          },
          {
            title: '电话',
            align: "center",
            dataIndex: 'phone'
          },
          {
            title: '操作',
            dataIndex: 'action',
            scopedSlots: {customRender: 'action'},
            align: "center",
            width: 150
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
  /** Button按钮间距 */
  .ant-btn {
    margin-left: 3px
  }

  .ant-card {
    margin-left: -30px;
    margin-right: -30px;
  }

  .table-page-search-wrapper {
    margin-top: -16px;
    margin-bottom: 16px;
  }
</style>