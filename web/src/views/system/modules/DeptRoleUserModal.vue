<template>
  <a-drawer
    :title="title"
    :maskClosable="true"
    width=600
    placement="right"
    :closable="true"
    @close="close"
    :visible="visible"
    style="height: calc(100% - 55px);overflow: auto;padding-bottom: 53px;">

    <a-spin :spinning="confirmLoading || loading">

      <a-alert v-if="loadError || saveError" type="error" show-icon style="margin-bottom: 16px">
        <span slot="message">{{ loadError || saveError }} <a @click="loadRoleData()">重新读取</a></span>
      </a-alert>
      <a-form :form="form" v-if="designNameOption.length>0">
        <a-form-item label=''>
          <a-col :xl="24" :lg="24" :md="24" :sm="24" :xs="24">
            <a-card :style="{ marginTop: '12px',height:'auto' }">
              <a-checkbox-group @change="designNameChange" v-model="designNameValue" style="width: 100%">
                <a-row>
                  <template v-for="(des) in designNameOption">
                    <a-col :span="6">
                      <a-checkbox :value="des.value">{{ des.text }}</a-checkbox>
                    </a-col>
                  </template>
                </a-row>
              </a-checkbox-group>
            </a-card>
          </a-col>
        </a-form-item>
      </a-form>
      <div v-else><h3>无可配置角色!</h3></div>
    </a-spin>
    <div class="drawer-bootom-button">
      <a-dropdown style="float: left" :trigger="['click']" placement="topCenter">
        <a-menu slot="overlay">
          <a-menu-item key="1" @click="checkALL">全部勾选</a-menu-item>
          <a-menu-item key="2" @click="cancelCheckALL">取消全选</a-menu-item>
        </a-menu>
        <a-button :disabled="!ready || confirmLoading">
          操作 <a-icon type="up" />
        </a-button>
      </a-dropdown>
      <a-button @click="confirmCancel" style="margin-right: .8rem">取消</a-button>
      <a-button @click="handleSubmit(true)" :disabled="!ready || !designNameOption.length" :loading="confirmLoading" type="primary">保存</a-button>
    </div>
  </a-drawer>
</template>

<script>
  import {httpAction, getAction} from '@/api/manage'
  import  JEllipsis  from '@/components/jeecg/JEllipsis'
  import {initDictOptions} from '@/components/dict/JDictSelectUtil'

  export default {
    name: 'DeptRoleUserModal',
    components: {
      JEllipsis
    },
    data() {
      return {
        currentDeptId:"",
        title: "部门角色分配",
        visible: false,
        model: {},
        labelCol: {
          xs: {span: 24},
          sm: {span: 5},
        },
        wrapperCol: {
          xs: {span: 24},
          sm: {span: 16},
        },
        confirmLoading: false,
        loading: false,
        ready: false,
        sessionVersion: 0,
        loadRequestId: 0,
        editContext: null,
        cancelPrompt: null,
        loadError: '',
        saveError: '',
        form: this.$form.createForm(this),
        validatorRules: {},
        url: {
          add: "/sys/sysDepartRole/deptRoleUserAdd",
          getDeptRoleList:"/sys/sysDepartRole/getDeptRoleList",
          getDeptRoleByUserId:"/sys/sysDepartRole/getDeptRoleByUserId"
        },
        designNameOption: [],
        userId: "",
        newRoleId:"",
        oldRoleId:"",
        designNameValue:[],
        desformList: [],
      }
    },
    beforeDestroy() { this.close() },
    methods: {
      add(record, departId, context) {
        this.userId = record.id
        this.currentDeptId = departId
        return this.edit({}, context)
      },
      edit(record, context) {
        this.sessionVersion++
        this.loadRequestId++
        this.editContext = context ? Object.assign({}, context) : null
        this.form.resetFields()
        this.model = Object.assign({}, record)
        this.visible = true
        this.confirmLoading = false
        this.cancelPrompt = null
        this.saveError = ''
        return this.loadRoleData()
      },
      isCurrentSession(version) {
        return this.visible && version === this.sessionVersion && (!this.editContext || !this.editContext.isCurrent || this.editContext.isCurrent())
      },
      loadRoleData() {
        if (!this.visible || !this.currentDeptId || !this.userId) return
        const version = this.sessionVersion
        const requestId = ++this.loadRequestId
        const userId = this.userId, departId = this.currentDeptId
        this.loading = true
        this.ready = false
        this.loadError = ''
        this.designNameOption = []
        this.designNameValue = []
        this.desformList = []
        this.newRoleId = ''
        this.oldRoleId = ''
        const isCurrent = () => this.isCurrentSession(version) && requestId === this.loadRequestId && userId === this.userId && departId === this.currentDeptId
        return Promise.all([
          getAction(this.url.getDeptRoleList, { departId, userId }),
          getAction(this.url.getDeptRoleByUserId, { userId })
        ]).then(([options, assigned]) => {
          if (!isCurrent()) return
          const validOptions = options && options.success === true && Array.isArray(options.result) && options.result.every(row => row && typeof row.id === 'string' && row.id)
          const validAssigned = assigned && assigned.success === true && Array.isArray(assigned.result) && assigned.result.every(row => row && typeof row.droleId === 'string' && row.droleId)
          if (!validOptions || !validAssigned) { this.loadError = '部门角色读取未完成，请重试后保存。'; return }
          this.desformList = options.result
          this.designNameOption = options.result.map(row => ({ value: row.id, text: row.roleName }))
          const ids = assigned.result.map(row => row.droleId).filter(id => options.result.some(row => row.id === id))
          this.designNameValue = ids.slice()
          this.oldRoleId = ids.join(',')
          this.newRoleId = ids.join(',')
          this.ready = true
        }).catch(() => { if (isCurrent()) this.loadError = '部门角色读取未完成，请重试后保存。' })
          .finally(() => { if (isCurrent()) this.loading = false })
      },
      loadDesformList() { return this.loadRoleData() },
      close() {
        this.sessionVersion++
        this.loadRequestId++
        this.visible = false
        this.editContext = null
        this.confirmLoading = false
        this.loading = false
        this.ready = false
        this.cancelPrompt = null
        this.designNameOption = []
        this.designNameValue = []
        this.desformList = []
        this.newRoleId = ''
        this.oldRoleId = ''
        this.$emit('close')
      },
      confirmCancel() {
        if (!this.visible || this.cancelPrompt) return
        const prompt = { version: this.sessionVersion }
        this.cancelPrompt = prompt
        this.$confirm({ title: '确定放弃编辑？',
          onOk: () => { if (this.cancelPrompt === prompt && this.isCurrentSession(prompt.version)) this.close() },
          onCancel: () => { if (this.cancelPrompt === prompt) this.cancelPrompt = null }
        })
      },
      handleCancel() { this.close() },
      handleSubmit() {
        const version = this.sessionVersion
        if (!this.isCurrentSession(version) || !this.ready || this.loading || this.confirmLoading || !this.designNameOption.length) return
        const context = this.editContext ? Object.assign({}, this.editContext) : null
        const formData = Object.assign({}, this.model, { userId: this.userId, newRoleId: this.newRoleId, oldRoleId: this.oldRoleId })
        this.confirmLoading = true
        this.saveError = ''
        return httpAction(this.url.add, formData, 'post').then(res => {
          if (!this.isCurrentSession(version)) return
          if (res && res.success === true) {
            this.$message.success(res.message || '部门角色已保存')
            this.$emit('reload')
            if (context) this.$emit('ok', context)
            else this.$emit('ok')
            if (this.isCurrentSession(version)) this.close()
          } else this.saveError = '部门角色未保存成功，请重试。'
        }).catch(() => { if (this.isCurrentSession(version)) this.saveError = '未能确认保存结果，请重新读取角色核对后重试。' })
          .finally(() => { if (this.isCurrentSession(version)) this.confirmLoading = false })
      },
      designNameChange(values) {
        if (!this.ready || this.confirmLoading || !values.every(id => this.designNameOption.some(row => row.value === id))) return
        this.designNameValue = values.slice()
        this.newRoleId = values.join(',')
      },
      checkALL() { if (this.ready && !this.confirmLoading) this.designNameChange(this.desformList.map(row => row.id)) },
      cancelCheckALL() { if (this.ready && !this.confirmLoading) this.designNameChange([]) }
    }

  }
</script>

<style scoped>
  .drawer-bootom-button {
    position: absolute;
    bottom: 0;
    width: 100%;
    border-top: 1px solid #e8e8e8;
    padding: 10px 16px;
    text-align: right;
    left: 0;
    background: #fff;
    border-radius: 0 0 2px 2px;
  }
</style>
