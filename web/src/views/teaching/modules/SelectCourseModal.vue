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
        <a-form layout="inline">
          <a-row :gutter="24">

            <a-col :span="10">
              <a-form-item label="课程名">
                <a-input placeholder="请输入课程名" v-model="queryParam.courseName"></a-input>
              </a-form-item>
            </a-col>
            <a-col :span="8">
                    <span style="float: left;overflow: hidden;" class="table-page-search-submitButtons">
                      <a-button type="primary" :loading="loading" @click="searchQuery" icon="search">查询</a-button>
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

  export default {
    name: "SelectCourseModal",
    data() {
      return {
        title: "选择课程",
        names: [],
        visible: false,
        departId: '',
        contextVersion: null,
        sessionVersion: 0,
        listRequestId: 0,
        loadError: '',
        placement: 'right',
        description: '',
        // 查询条件
        queryParam: {},
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
            title:'课程名',
            align:"center",
            width: 100,
            dataIndex: 'courseName'
          },
          // {
          //   title:'课程介绍',
          //   align:"center",
          //   width: 200,
          //   dataIndex: 'courseDesc'
          // },
          {
            title:'创建时间',
            align:"center",
            width: 150,
            dataIndex: 'createTime'
          }
        ],
        columns2: [
          {
            title:'课程名',
            align:"center",
            dataIndex: 'courseName'
          },

          {
            title:'课程介绍',
            align:"center",
            dataIndex: 'courseDesc'
          },
           {
            title:'创建时间',
            align:"center",
            dataIndex: 'createTime'
          },
 
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
          list: "/teaching/teachingCourse/list",
        }
      }
    },
    created() {
      // this.loadData();
    },
    beforeDestroy() {
      this.handleCancel()
    },
    methods: {
      show(departId, contextVersion){
        this.sessionVersion++
        this.listRequestId++
        this.departId = departId || ''
        this.contextVersion = contextVersion
        this.queryParam = { departId: this.departId }
        this.onClearSelected()
        this.dataSource1 = []
        this.dataSource2 = []
        this.ipagination.current = 1
        this.ipagination.total = 0
        this.loading = false
        this.loadError = ''
        this.visible = true
        return this.loadData(1);
      },
      searchQuery() {
        this.loadData(1);
      },
      handleCancel() {
        this.sessionVersion++
        this.listRequestId++
        this.visible = false
        this.loading = false
        this.loadError = ''
        this.departId = ''
        this.onClearSelected()
        this.dataSource1 = []
        this.dataSource2 = []
        this.ipagination.current = 1
        this.ipagination.total = 0
      },
      handleOk() {
        if (!this.visible || !this.departId || this.loading || this.loadError) return
        if (this.selectedRowKeys.length === 0) {
          this.$message.warning('请选择课程！')
          return
        }
        const selection = {
          deptId: this.departId,
          contextVersion: this.contextVersion,
          courseIdList: this.selectedRowKeys.slice()
        }
        this.handleCancel()
        this.$emit("selectFinished", selection)
      },
      add() {
        return this.show(this.departId, this.contextVersion)
      },
      loadData(arg) {
        if (!this.visible || !this.departId) return
        //加载数据 若传入参数1则加载第一页的内容
        if (arg === 1) {
          this.ipagination.current = 1;
        }
        const sessionVersion = this.sessionVersion
        const departId = this.departId
        const requestId = ++this.listRequestId
        const params = Object.assign({}, this.getQueryParams(), { departId })
        this.loading = true
        this.loadError = ''
        this.dataSource1 = []
        this.ipagination.total = 0
        this.onClearSelected()
        const isCurrent = () => this.visible && sessionVersion === this.sessionVersion && requestId === this.listRequestId && departId === this.departId
        return getAction(this.url.list, params).then((res) => {
          if (!isCurrent()) return
          if (res && res.success === true && res.result && this.isValidRecords(res.result.records)) {
            this.dataSource1 = res.result.records;
            this.ipagination.total = Number(res.result.total) || 0;
          } else {
            this.loadError = '课程列表加载失败，请重试。'
          }
        }).catch(() => {
          if (isCurrent()) this.loadError = '课程列表加载失败，请重试。'
        }).finally(() => {
          if (isCurrent()) this.loading = false
        })
      },
      getQueryParams() {
        var param = Object.assign({}, this.queryParam, this.isorter);
        param.field = this.getQueryField();
        param.pageNo = this.ipagination.current;
        param.pageSize = this.ipagination.pageSize;
        return filterObj(param);
      },
      getQueryField() {
        //TODO 字段权限控制
      },
      isValidRecords(records) {
        return Array.isArray(records) && records.every(row => row && typeof row === 'object' && !Array.isArray(row) && (typeof row.id === 'string' || typeof row.id === 'number') && row.id !== '')
      },
      onSelectChange(selectedRowKeys, selectedRows) {
        if (!this.visible || this.loading || this.loadError || !selectedRowKeys.every(id => this.dataSource1.some(row => row.id === id))) return
        this.selectedRowKeys = selectedRowKeys.slice();
        this.selectionRows = selectedRows.slice();
      },
      onClearSelected() {
        this.selectedRowKeys = [];
        this.selectionRows = [];
      },
      handleTableChange(pagination, filters, sorter) {
        //分页、排序、筛选变化时触发
        //TODO 筛选
        if (Object.keys(sorter).length > 0) {
          this.isorter.column = sorter.field;
          this.isorter.order = "ascend" == sorter.order ? "asc" : "desc"
        }
        this.ipagination = pagination;
        this.loadData();
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
