<template>
  <a-card :bordered="false">
    <!-- 操作按钮区域 -->
    <div class="table-operator" :md="24" :sm="24" style="margin: 0 0px 10px 2px">
      <a-button :disabled="currentDept.orgCategory!=3 || operationsDisabled" @click="handleAddCourse" type="primary" icon="plus">添加已有课程</a-button>

      <a-dropdown v-if="selectedRowKeys.length > 0">
        <a-menu slot="overlay">
          <a-menu-item key="1" @click="batchDel">
            <a-icon type="delete" />删除关系
          </a-menu-item>
        </a-menu>
        <a-button :disabled="operationsDisabled" style="margin-left: 8px">
          批量操作
          <a-icon type="down" />
        </a-button>
      </a-dropdown>
    </div>

    <!-- table区域-begin -->
    <div>
      <a-alert v-if="listError" type="error" show-icon style="margin-bottom: 16px">
        <span slot="message">{{ listError }} <a @click="loadData()">重试</a></span>
      </a-alert>
      <div class="ant-alert ant-alert-info" style="margin-bottom: 16px;">
        <i class="anticon anticon-info-circle ant-alert-icon"></i> 已选择
        <a style="font-weight: 600">
          {{
          selectedRowKeys.length }}
        </a>项
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
        :loading="loading || mutationLoading"
        :rowSelection="{selectedRowKeys: selectedRowKeys, onChange: onSelectChange}"
        @change="handleTableChange"
      >
        <span slot="action" slot-scope="text, record">
          <a :disabled="operationsDisabled" @click="handleEditCourse(record)">设置开课时间</a>

          <!-- <a @click="setOpenTime(record)">开课时间</a> -->

          <a-divider type="vertical" />

          <a :disabled="operationsDisabled" @click="confirmDelete(record)">删除</a>

          <a-divider type="vertical" />
        </span>
      </a-table>
    </div>
    <!-- table区域-end -->

    <!-- 表单区域 -->
    <teachingCourseDept-modal ref="editCourse" @ok="modalFormOk"></teachingCourseDept-modal>

    <Select-Course-Modal ref="selectCourseModal" @selectFinished="selectOK"></Select-Course-Modal>
  </a-card>
</template>

<script>
import { JeecgListMixin } from '@/mixins/JeecgListMixin'
import { getAction, postAction, deleteAction } from '@/api/manage'
import SelectCourseModal from '@/views/teaching/modules/SelectCourseModal'
import TeachingCourseDeptModal from '@/views/teaching/modules/TeachingCourseDeptModal'

export default {
  name: 'DeptCourseInfo',
  mixins: [JeecgListMixin],
  components: {
    SelectCourseModal,
    TeachingCourseDeptModal
  },
  data() {
    return {
      description: '课程信息',
      currentDeptId: '',
      currentDept: {},
      contextVersion: 0,
      listRequestId: 0,
      selectionVersion: 0,
      writeRequestId: 0,
      mutationLoading: false,
      deletePrompt: null,
      listError: '',
      // 表头
      columns: [
        // {
        //   title: '课程ID',
        //   align: 'center',
        //   dataIndex: 'courseId'
        // },
        {
          title: '课程名',
          align: 'center',
          dataIndex: 'courseName'
        },
        {
          title: '开课时间',
          align: 'center',
          dataIndex: 'openTime'
        },
        {
          title: '操作',
          dataIndex: 'action',
          scopedSlots: { customRender: 'action' },
          align: 'center',
          width: 170
        }
      ],
      isorter: {
        column: 'teachingCourseDept.createTime',
        order: 'desc'
      },
      url: {
        list: '/teaching/teachingCourseDept/list',
        add: '/teaching/teachingCourseDept/add',
        addOrUpdate: '/teaching/teachingCourseDept/addOrUpdate',
        edit: '/teaching/teachingCourseDept/edit',
        delete: '/teaching/teachingCourseDept/delete',
        deleteBatch: '/teaching/teachingCourseDept/deleteBatch'
      }
    }
  },
  created() {},
  computed: {
    operationsDisabled() {
      return !this.currentDeptId || this.loading || this.mutationLoading || !!this.listError
    }
  },
  beforeDestroy() {
    this.clearList()
  },

  methods: {
    loadData(arg) {
      if (!this.url.list) {
        this.$message.error('请设置url.list属性!')
        return
      }
      if (arg === 1) {
        this.ipagination.current = 1
      }
      if (!this.currentDeptId) return
      const context = this.captureContext()
      const requestId = ++this.listRequestId
      const params = Object.assign({}, this.getQueryParams(), { deptId: context.deptId })
      this.loading = true
      this.listError = ''
      this.dataSource = []
      this.ipagination.total = 0
      this.onClearSelected()
      const isCurrent = () => this.isCurrentContext(context) && requestId === this.listRequestId
      return getAction(this.url.list, params).then(res => {
        if (!isCurrent()) return
        if (res && res.success === true && res.result && this.isValidRecords(res.result.records)) {
          this.dataSource = res.result.records
          this.ipagination.total = Number(res.result.total) || 0
        } else {
          this.listError = '课程关系加载失败，请重试。'
        }
      }).catch(() => {
        if (isCurrent()) this.listError = '课程关系加载失败，请重试。'
      }).finally(() => {
        if (isCurrent()) this.loading = false
      })
    },
    batchDel: function() {
      if (!this.url.deleteBatch) {
        this.$message.error('请设置url.deleteBatch属性!')
        return
      }
      if (this.operationsDisabled || this.deletePrompt) return
      if (this.selectedRowKeys.length <= 0) {
        this.$message.warning('请选择一条记录！')
        return
      }
      const snapshot = Object.assign(this.captureContext(), {
        relationIds: this.selectedRowKeys.slice(),
        selectionVersion: this.selectionVersion
      })
      this.deletePrompt = snapshot
      this.$confirm({
        title: '确认删除',
        content: `是否删除班级“${this.currentDept.departName || snapshot.deptId}”选中的课程关系?`,
        onOk: () => this.confirmDeletion(snapshot, true),
        onCancel: () => this.cancelDeletion(snapshot)
      })
    },
    confirmDelete(record) {
      if (this.operationsDisabled || this.deletePrompt || !this.isCurrentRelation(record)) return
      const snapshot = Object.assign(this.captureContext(), { relationIds: [record.id], record })
      this.deletePrompt = snapshot
      this.$confirm({
        title: '确认删除',
        content: `是否删除班级“${this.currentDept.departName || snapshot.deptId}”的这条课程关系?`,
        onOk: () => this.confirmDeletion(snapshot, false),
        onCancel: () => this.cancelDeletion(snapshot)
      })
    },
    confirmDeletion(snapshot, batch) {
      if (this.deletePrompt !== snapshot) return
      this.deletePrompt = null
      return batch ? this.deleteRelations(snapshot, true) : this.handleDelete(snapshot.relationIds[0], snapshot)
    },
    cancelDeletion(snapshot) {
      if (this.deletePrompt === snapshot) this.deletePrompt = null
    },
    handleDelete: function(id, snapshot) {
      if (!this.url.delete) {
        this.$message.error('请设置url.delete属性!')
        return
      }
      if (!snapshot || snapshot.relationIds[0] !== id) return
      return this.deleteRelations(snapshot, false)
    },
    open(record) {
      this.resetContext(record)
      return this.loadData(1)
    },
    clearList() {
      this.resetContext()
    },
    resetContext(record) {
      this.contextVersion++
      this.listRequestId++
      this.currentDept = Object.assign({}, record || {})
      this.currentDeptId = record && record.id ? record.id : ''
      this.onClearSelected()
      this.dataSource = []
      this.ipagination.current = 1
      this.ipagination.total = 0
      this.loading = false
      this.listError = ''
      this.mutationLoading = false
      this.deletePrompt = null
      if (this.$refs.selectCourseModal) this.$refs.selectCourseModal.handleCancel()
      if (this.$refs.editCourse) this.$refs.editCourse.close()
    },
    captureContext() {
      return { deptId: this.currentDeptId, contextVersion: this.contextVersion }
    },
    isCurrentContext(context) {
      return !!context && !!context.deptId && context.deptId === this.currentDeptId && context.contextVersion === this.contextVersion
    },
    isCurrentRelation(record) {
      return !!record && this.dataSource.indexOf(record) !== -1 && (!record.deptId || record.deptId === this.currentDeptId)
    },
    isValidRecords(records) {
      return Array.isArray(records) && records.every(row => row && typeof row === 'object' && !Array.isArray(row) && (typeof row.id === 'string' || typeof row.id === 'number') && row.id !== '')
    },
    onSelectChange(keys, rows) {
      if (this.operationsDisabled || !keys.every(id => this.dataSource.some(row => row.id === id))) return
      this.selectedRowKeys = keys.slice()
      this.selectionRows = rows.slice()
      this.selectionVersion++
    },
    onClearSelected() {
      this.selectedRowKeys = []
      this.selectionRows = []
      this.selectionVersion++
    },
    deleteRelations(snapshot, batch) {
      const ids = snapshot.relationIds
      const sameSelection = !batch || (snapshot.selectionVersion === this.selectionVersion && ids.length === this.selectedRowKeys.length && ids.every(id => this.selectedRowKeys.indexOf(id) !== -1))
      const currentRelations = ids.length > 0 && ids.every(id => this.dataSource.some(row => row.id === id && (!row.deptId || row.deptId === snapshot.deptId)))
      if (!this.isCurrentContext(snapshot) || !sameSelection || !currentRelations || (!batch && !this.isCurrentRelation(snapshot.record))) {
        this.$message.warning('班级或选择已变化，请重新选择课程关系。')
        return
      }
      if (this.operationsDisabled) return
      const requestId = ++this.writeRequestId
      this.mutationLoading = true
      const isCurrent = () => this.isCurrentContext(snapshot) && requestId === this.writeRequestId
      const url = batch ? this.url.deleteBatch : this.url.delete
      const params = batch ? { ids: ids.join(',') + ',' } : { id: ids[0] }
      return deleteAction(url, params).then(res => {
        if (!isCurrent()) return
        if (res && res.success === true) {
          this.$message.success(res.message || '删除成功')
          return this.loadData()
        }
        this.$message.warning('删除未成功，请重试。')
      }).catch(() => {
        if (isCurrent()) this.$message.warning('未能确认删除结果，请刷新列表后核对。')
      }).finally(() => {
        if (isCurrent()) this.mutationLoading = false
      })
    },
    hasSelectDept() {
      if (!this.currentDeptId) {
        this.$message.error('请选择一个部门!')
        return false
      }
      return true
    },
    handleAddCourse() {
      if (this.operationsDisabled || this.currentDept.orgCategory != 3) return
      this.$refs.selectCourseModal.show(this.currentDeptId, this.contextVersion)
    },
    handleEditCourse(record) {
      if (this.operationsDisabled || !this.isCurrentRelation(record)) return
      const context = this.captureContext()
      context.isCurrent = () => this.isCurrentContext(context)
      this.$refs.editCourse.edit(record, context)
      this.$refs.editCourse.title = '编辑'
      this.$refs.editCourse.disableSubmit = false
    },
    modalFormOk(context) {
      if (this.isCurrentContext(context)) return this.loadData()
    },
    selectOK(data) {
      if (!this.isCurrentContext(data)) {
        this.$message.warning('班级已变化，请重新选择课程。')
        return
      }
      if (this.operationsDisabled || this.currentDept.orgCategory != 3 || !Array.isArray(data.courseIdList) || data.courseIdList.length === 0) return
      const context = this.captureContext()
      const params = { deptId: data.deptId, courseIdList: data.courseIdList.slice() }
      const requestId = ++this.writeRequestId
      this.mutationLoading = true
      const isCurrent = () => this.isCurrentContext(context) && requestId === this.writeRequestId
      return postAction(this.url.addOrUpdate, params).then(res => {
        if (!isCurrent()) return
        if (res && res.success === true) {
          this.$message.success(res.message || '添加成功')
          return this.loadData()
        }
        this.$message.warning('添加未成功，请重新选择课程后重试。')
      }).catch(() => {
        if (isCurrent()) this.$message.warning('未能确认添加结果，请刷新列表后核对。')
      }).finally(() => {
        if (isCurrent()) this.mutationLoading = false
      })
    }
  }
}
</script>
<style scoped>
/** Button按钮间距 */
.ant-btn {
  margin-left: 3px;
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
