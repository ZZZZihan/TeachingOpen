<template>
  <div>
    <a-modal
      centered
      :title="title"
      width="calc(100vw - 32px)"
      wrapClassName="member-selector-dialog"
      :visible="visible"
      :okButtonProps="{props: {disabled: loading || !!loadError || selectedRowKeys.length === 0}}"
      @ok="handleOk"
      @cancel="handleCancel"
      cancelText="关闭">
      <p class="member-selector-intro">{{ selectionContext && selectionContext.deptId ? '查找已有用户，选择后加入当前班级。' : '查找并选择已有用户。' }}</p>
      <div class="member-selector-search-panel">
        <a-form layout="vertical" class="member-selector-search-form" @keyup.enter.native="searchQuery">
          <a-form-item label="用户账号" :htmlFor="'member-selector-username-' + _uid">
            <a-input :id="'member-selector-username-' + _uid" placeholder="请输入用户账号" v-model="queryParam.username"></a-input>
          </a-form-item>
          <a-form-item label="角色" :htmlFor="'member-selector-role-' + _uid">
            <a-select :id="'member-selector-role-' + _uid" v-model="queryParam.roleId" mode="single" defaultValue="" placeholder="请选择角色查询">
              <a-select-option value="">全部</a-select-option>
              <a-select-option v-for="(role,index) in roleList" :key="index.toString()" :value="role.id">{{role.roleName}}</a-select-option>
            </a-select>
          </a-form-item>
          <div class="member-selector-search-actions">
            <a-button type="primary" @click="searchQuery" icon="search">查询</a-button>
            <a-button @click="searchReset" icon="reload">重置</a-button>
          </div>
        </a-form>
      </div>
      <a-alert v-if="loadError" class="member-selector-feedback" type="error" show-icon>
        <span slot="message">{{ loadError }} <a href="#" @click.prevent="loadData()">重试</a></span>
      </a-alert>
      <a-alert v-if="roleError" class="member-selector-feedback" type="warning" show-icon>
        <span slot="message">{{ roleError }} <a href="#" @click.prevent="initialRoleList()">重试角色选项</a></span>
      </a-alert>
      <div class="member-selector-summary">
        <span role="status" aria-live="polite">已选择 <strong>{{ selectedRowKeys.length }}</strong> 位用户</span>
        <p>表格可横向滚动，聚焦后用 ← → 查看。</p>
      </div>
      <div
        class="member-selector-table-region"
        role="region"
        tabindex="0"
        aria-label="可选用户表格，左右方向键横向滚动"
        @keydown.left.self.prevent="$event.currentTarget.querySelector('.ant-table-body').scrollLeft -= 120"
        @keydown.right.self.prevent="$event.currentTarget.querySelector('.ant-table-body').scrollLeft += 120">
        <a-table
          size="small"
          bordered
          rowKey="id"
          :columns="columns1"
          :dataSource="dataSource1"
          :pagination="ipagination"
          :loading="loading"
          :scroll="{ x: 920, y: 240 }"
          :rowSelection="{selectedRowKeys: selectedRowKeys, onChange: onSelectChange, columnWidth: 64}"
          @change="handleTableChange">
        </a-table>
      </div>
    </a-modal>
  </div>
</template>

<script>
  import {filterObj} from '@/utils/util'
  import {getAction} from '@/api/manage'
  import {queryMySubRole} from '@/api/api'

  export default {
    name: "SelectUserModal",
    data() {
      return {
        title: "添加已有用户",
        names: [],
        visible: false,
        sessionActive: false,
        sessionVersion: 0,
        listRequestId: 0,
        roleRequestId: 0,
        selectionContext: null,
        loadError: '',
        roleError: '',
        roleLoading: false,
        placement: 'right',
        description: '',
        // 查询条件
        queryParam: {},
        roleList:[],
        // 表头
        columns1: [
          {
            title: '#',
            dataIndex: '',
            key: 'rowIndex',
            width: 56,
            align: "center",
            customRender: function (t, r, index) {
              return parseInt(index) + 1;
            }
          },
          {
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
            title: '电话',
            align: "center",
            width: 150,
            dataIndex: 'phone'
          },
          {
            title: '角色',
            align: 'center',
            dataIndex: 'roleNames',
            width: 180,
            customRender: function(value){
              return Array.isArray(value)?value.join():"--"
            }
          },
          {
           title: '部门',
           align: 'center',
            dataIndex: 'departNames',
            width: 180,
            customRender: function(value){
              return Array.isArray(value)?value.join():"--"
            }
          },
        ],
        columns2: [
          {
            title: '用户账号',
            align: "center",
            dataIndex: 'username',

          },
          {
            title: '用户名称',
            align: "center",
            dataIndex: 'realname',
          },
          {
            title: '操作',
            dataIndex: 'action',
            align: "center",
            width: 100,
            scopedSlots: {customRender: 'action'},
          }
        ],
        //数据集
        dataSource1: [],
        dataSource2: [],
        // 分页参数
        ipagination: {
          current: 1,
          pageSize: 10,
          pageSizeOptions: ['10', '20', '30'],
          showTotal: (total, range) => {
            return range[0] + "-" + range[1] + " 共" + total + "条"
          },
          showQuickJumper: true,
          showSizeChanger: true,
          total: 0
        },
        isorter: {
          column: 'createTime',
          order: 'desc',
        },
        loading: false,
        selectedRowKeys: [],
        selectionRows: [],
        url: {
          list: "/sys/user/list",
        }
      }
    },
    watch: {
      visible(value) {
        if (value && !this.sessionActive) this.show()
        else if (!value && this.sessionActive) this.handleCancel()
      }
    },
    beforeDestroy() { this.handleCancel() },
    methods: {
      show(context) {
        this.sessionVersion++
        this.listRequestId++
        this.roleRequestId++
        this.sessionActive = true
        this.selectionContext = context ? Object.assign({}, context) : null
        this.queryParam = {}
        this.onClearSelected()
        this.dataSource1 = []
        this.dataSource2 = []
        this.roleList = []
        this.ipagination.current = 1
        this.ipagination.total = 0
        this.loadError = ''
        this.roleError = ''
        this.visible = true
        return Promise.all([this.loadData(1), this.initialRoleList()])
      },
      add() { return this.show() },
      initialRoleList() {
        if (!this.visible || !this.sessionActive) return
        const sessionVersion = this.sessionVersion
        const requestId = ++this.roleRequestId
        this.roleLoading = true
        this.roleError = ''
        const isCurrent = () => this.visible && sessionVersion === this.sessionVersion && requestId === this.roleRequestId
        return queryMySubRole().then(res => {
          if (!isCurrent()) return
          if (res && res.success === true && this.isValidRecords(res.result)) this.roleList = res.result
          else this.roleError = '角色选项加载失败，可重试或按账号查询。'
        }).catch(() => {
          if (isCurrent()) this.roleError = '角色选项加载失败，可重试或按账号查询。'
        }).finally(() => { if (isCurrent()) this.roleLoading = false })
      },
      searchQuery() { return this.loadData(1) },
      searchReset() { this.queryParam = {}; return this.loadData(1) },
      handleCancel() {
        this.sessionVersion++
        this.listRequestId++
        this.roleRequestId++
        this.visible = false
        this.sessionActive = false
        this.selectionContext = null
        this.loading = false
        this.roleLoading = false
        this.loadError = ''
        this.roleError = ''
        this.onClearSelected()
        this.dataSource1 = []
        this.dataSource2 = []
        this.ipagination.current = 1
        this.ipagination.total = 0
      },
      handleOk() {
        if (!this.visible || !this.sessionActive || this.loading || this.loadError || !this.selectedRowKeys.length) return
        const ids = this.selectedRowKeys.slice()
        const payload = this.selectionContext ? Object.assign({}, this.selectionContext, { userIdList: ids }) : ids
        this.handleCancel()
        this.$emit('selectFinished', payload)
      },
      loadData(arg) {
        if (!this.visible || !this.sessionActive) return
        if (arg === 1) this.ipagination.current = 1
        const sessionVersion = this.sessionVersion
        const requestId = ++this.listRequestId
        const params = this.getQueryParams()
        this.loading = true
        this.loadError = ''
        this.dataSource1 = []
        this.ipagination.total = 0
        this.onClearSelected()
        const isCurrent = () => this.visible && sessionVersion === this.sessionVersion && requestId === this.listRequestId
        return getAction(this.url.list, params).then(res => {
          if (!isCurrent()) return
          if (res && res.success === true && res.result && this.isValidRecords(res.result.records)) {
            this.dataSource1 = res.result.records
            this.ipagination.total = Number(res.result.total) || 0
          } else this.loadError = '用户列表加载失败，请重试。'
        }).catch(() => { if (isCurrent()) this.loadError = '用户列表加载失败，请重试。' })
          .finally(() => { if (isCurrent()) this.loading = false })
      },
      isValidRecords(records) {
        return Array.isArray(records) && records.every(row => row && typeof row === 'object' && !Array.isArray(row) && (typeof row.id === 'string' || typeof row.id === 'number') && row.id !== '')
      },
      getQueryParams() {
        const params = Object.assign({}, this.queryParam, this.isorter)
        params.field = this.getQueryField()
        params.pageNo = this.ipagination.current
        params.pageSize = this.ipagination.pageSize
        return filterObj(params)
      },
      getQueryField() {},
      onSelectChange(keys, rows) {
        if (!this.visible || this.loading || this.loadError || !keys.every(id => this.dataSource1.some(row => row.id === id))) return
        this.selectedRowKeys = keys.slice()
        this.selectionRows = rows.slice()
      },
      onClearSelected() { this.selectedRowKeys = []; this.selectionRows = [] },
      handleTableChange(pagination, filters, sorter) {
        if (Object.keys(sorter).length > 0) {
          this.isorter.column = sorter.field
          this.isorter.order = sorter.order === 'ascend' ? 'asc' : 'desc'
        }
        this.ipagination = pagination
        return this.loadData()
      }
    }
  }
</script>
<style>
.member-selector-dialog .ant-modal {
  max-width: 1000px;
  padding-bottom: 0;
}
.member-selector-dialog .ant-modal-content {
  border-radius: 8px;
}
.member-selector-dialog .ant-modal-header {
  padding: 20px 24px;
  border-bottom-color: #eee8ed;
}
.member-selector-dialog .ant-modal-title {
  color: #29222b;
  font-size: 18px;
  font-weight: 600;
}
.member-selector-dialog .ant-modal-body {
  max-height: calc(100vh - 176px);
  padding: 20px 24px;
  overflow-y: auto;
}
.member-selector-dialog .ant-modal-footer {
  padding: 14px 24px;
  border-top-color: #eee8ed;
}
.member-selector-dialog .ant-modal-footer > div {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}
.member-selector-dialog .ant-modal-footer button + button {
  margin-left: 0;
}
.member-selector-dialog .member-selector-intro {
  margin: 0 0 16px;
  color: #6e6570;
  line-height: 1.6;
}
.member-selector-dialog .member-selector-search-panel {
  padding: 16px;
  border: 1px solid #e9e2e8;
  border-radius: 6px;
  background: #fcfafc;
}
.member-selector-dialog .member-selector-search-form {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr));
  align-items: end;
  gap: 12px 16px;
  min-width: 0;
}
.member-selector-dialog .ant-form-item {
  min-width: 0;
  margin: 0;
}
.member-selector-dialog .ant-form-item-label {
  padding-bottom: 6px;
  line-height: 1.4;
}
.member-selector-dialog .ant-form-item-label label {
  color: #534757;
  font-size: 13px;
}
.member-selector-dialog .ant-input,
.member-selector-dialog .ant-select-selection--single {
  height: 36px;
}
.member-selector-dialog .ant-select-selection__rendered {
  line-height: 34px;
}
.member-selector-dialog .member-selector-search-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.member-selector-dialog .member-selector-search-actions .ant-btn {
  flex: 1 1 auto;
  height: 36px;
}
.member-selector-dialog .ant-btn-primary:not([disabled]) {
  background: #74256a;
  border-color: #74256a;
}
.member-selector-dialog .ant-btn-primary:not([disabled]):hover {
  background: #592052;
  border-color: #592052;
}
.member-selector-dialog a {
  color: #74256a;
}
.member-selector-dialog .member-selector-feedback {
  margin-top: 16px;
  overflow-wrap: anywhere;
}
.member-selector-dialog .member-selector-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin: 16px 0 12px;
  color: #534757;
}
.member-selector-dialog .member-selector-summary strong {
  color: #74256a;
}
.member-selector-dialog .member-selector-summary p {
  margin: 0;
  color: #6e6570;
  font-size: 12px;
  line-height: 1.6;
}
.member-selector-dialog .member-selector-table-region {
  width: 100%;
  min-width: 0;
  border-radius: 4px;
}
.member-selector-dialog .member-selector-table-region:focus-visible {
  outline: 2px solid #74256a;
  outline-offset: 3px;
}
.member-selector-dialog .ant-table-wrapper,
.member-selector-dialog .ant-spin-nested-loading,
.member-selector-dialog .ant-spin-container,
.member-selector-dialog .ant-table,
.member-selector-dialog .ant-table-content,
.member-selector-dialog .ant-table-scroll {
  min-width: 0;
  max-width: 100%;
}
.member-selector-dialog .ant-table-thead > tr > th {
  color: #534757;
  background: #f8f5f8;
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
}
.member-selector-dialog .ant-table-tbody > tr > td {
  overflow-wrap: anywhere;
}
.member-selector-dialog .ant-table-pagination.ant-pagination {
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
.member-selector-dialog .ant-pagination > li {
  margin: 0;
}
.member-selector-dialog .ant-pagination-options {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
}
.member-selector-dialog .ant-pagination-options-size-changer.ant-select {
  margin: 0;
}
@media (max-width: 480px) {
  .member-selector-dialog .ant-modal-header,
  .member-selector-dialog .ant-modal-body,
  .member-selector-dialog .ant-modal-footer {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
