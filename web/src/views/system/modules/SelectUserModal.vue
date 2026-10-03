<template>
  <div>
    <a-modal
      centered
      :title="title"
      :width="1000"
      :visible="visible"
      :okButtonProps="{props: {disabled: loading || !!loadError || selectedRowKeys.length === 0}}"
      @ok="handleOk"
      @cancel="handleCancel"
      cancelText="关闭">


      <!-- 查询区域 -->
      <div class="table-page-search-wrapper">
        <a-form layout="inline"  @keyup.enter.native="searchQuery">
          <a-row :gutter="24">

            <a-col :span="10">
              <a-form-item label="用户账号">
                <a-input placeholder="请输入用户账号" v-model="queryParam.username"></a-input>
              </a-form-item>
            </a-col>
            <a-col :span="10">
              <a-form-item label="角色">
                <a-select v-model="queryParam.roleId" mode="single" defaultValue="" placeholder="请选择角色查询">
                  <a-select-option value="">全部</a-select-option>
                  <a-select-option v-for="(role,index) in roleList" :key="index.toString()" :value="role.id">{{role.roleName}}</a-select-option>
                </a-select>
              </a-form-item>
              </a-col>
            <a-col :span="8">
                    <span style="float: left;overflow: hidden;" class="table-page-search-submitButtons">
                      <a-button type="primary" @click="searchQuery" icon="search">查询</a-button>
                      <a-button type="primary" @click="searchReset" icon="reload" style="margin-left: 8px">重置</a-button>
                    </span>
            </a-col>

          </a-row>
        </a-form>
      </div>
      <!-- table区域-begin -->
      <div>
        <a-alert v-if="loadError" type="error" show-icon style="margin-bottom: 16px">
          <span slot="message">{{ loadError }} <a @click="loadData()">重试</a></span>
        </a-alert>
        <a-alert v-if="roleError" type="warning" show-icon style="margin-bottom: 16px">
          <span slot="message">{{ roleError }} <a @click="initialRoleList()">重试角色选项</a></span>
        </a-alert>
        <a-table
          size="small"
          bordered
          rowKey="id"
          :columns="columns1"
          :dataSource="dataSource1"
          :pagination="ipagination"
          :loading="loading"
          :scroll="{ y: 240 }"
          :rowSelection="{selectedRowKeys: selectedRowKeys, onChange: onSelectChange}"
          @change="handleTableChange">

        </a-table>
      </div>
      <!-- table区域-end -->


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
            width: 50,
            align: "center",
            customRender: function (t, r, index) {
              return parseInt(index) + 1;
            }
          },
          {
            title: '用户账号',
            align: "center",
            width: 100,
            dataIndex: 'username'
          },
          {
            title: '用户名称',
            align: "center",
            width: 100,
            dataIndex: 'realname'
          },
          {
            title: '电话',
            align: "center",
            width: 100,
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
<style lang="less" scoped>
  .ant-card-body .table-operator {
    margin-bottom: 18px;
  }

  .ant-table-tbody .ant-table-row td {
    padding-top: 15px;
    padding-bottom: 15px;
  }

  .anty-row-operator button {
    margin: 0 5px
  }

  .ant-btn-danger {
    background-color: #ffffff
  }

  .ant-modal-cust-warp {
    height: 100%
  }

  .ant-modal-cust-warp .ant-modal-body {
    height: calc(100% - 110px) !important;
    overflow-y: auto
  }

  .ant-modal-cust-warp .ant-modal-content {
    height: 90% !important;
    overflow-y: hidden
  }
</style>