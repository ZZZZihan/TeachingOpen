<template>
  <a-modal
    :title="title"
    :width="width"
    :visible="visible"
    :confirmLoading="confirmLoading"
    @ok="handleOk"
    @cancel="handleCancel"
    cancelText="关闭">
    <a-spin :spinning="confirmLoading">
      <a-form :form="form">

        <a-form-item v-if="false" label="班级" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input v-decorator="[ 'deptId', validatorRules.deptId]" placeholder="请输入班级"></a-input>
        </a-form-item>
        <a-form-item v-if="false" label="课程" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input v-decorator="[ 'courseId', validatorRules.courseId]" placeholder="请输入课程"></a-input>
        </a-form-item>
        <a-form-item label="课程开课时间" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-date placeholder="请选择课程开课时间" v-decorator="[ 'openTime', validatorRules.openTime]" :dateFormat="'YYYY-MM-DD HH:mm:ss'" :showTime="true" :trigger-change="true" style="width: 100%"/>
        </a-form-item>

      </a-form>
    </a-spin>
  </a-modal>
</template>

<script>

  import { httpAction } from '@/api/manage'
  import pick from 'lodash.pick'
  import JDate from '@/components/jeecg/JDate'  

  export default {
    name: "TeachingCourseDeptModal",
    components: { 
      JDate,
    },
    data () {
      return {
        form: this.$form.createForm(this),
        title:"操作",
        width:800,
        visible: false,
        model: {},
        sessionVersion: 0,
        editContext: null,
        labelCol: {
          xs: { span: 24 },
          sm: { span: 5 },
        },
        wrapperCol: {
          xs: { span: 24 },
          sm: { span: 16 },
        },
        confirmLoading: false,
        validatorRules: {
          deptId: {rules: [
            {required: true, message: '请输入班级!'},
          ]},
          courseId: {rules: [
            {required: true, message: '请输入课程!'},
          ]},
          openTime: {rules: [
          ]},
        },
        url: {
          add: "/teaching/teachingCourseDept/add",
          edit: "/teaching/teachingCourseDept/edit",
        }
      }
    },
    created () {
    },
    beforeDestroy () {
      this.sessionVersion++
      this.visible = false
      this.confirmLoading = false
    },
    methods: {
      add () {
        this.edit({});
      },
      edit (record, context) {
        const sessionVersion = ++this.sessionVersion
        this.confirmLoading = false
        this.editContext = context ? Object.assign({}, context) : null
        this.form.resetFields();
        this.model = Object.assign({}, record);
        this.visible = true;
        this.$nextTick(() => {
          if (!this.isCurrentSession(sessionVersion)) return
          this.form.setFieldsValue(pick(this.model,'openTime'))
        })
      },
      close () {
        this.sessionVersion++
        this.visible = false;
        this.confirmLoading = false
        this.editContext = null
        this.form.resetFields()
        this.$emit('close');
      },
      isCurrentSession (sessionVersion) {
        return this.visible && sessionVersion === this.sessionVersion && (!this.editContext || !this.editContext.isCurrent || this.editContext.isCurrent())
      },
      handleOk () {
        if (!this.visible || this.confirmLoading) return
        const sessionVersion = this.sessionVersion
        if (!this.isCurrentSession(sessionVersion)) return
        const model = Object.assign({}, this.model)
        const context = this.editContext ? Object.assign({}, this.editContext) : null
        this.confirmLoading = true
        // 触发表单验证
        this.form.validateFields((err, values) => {
          if (!this.isCurrentSession(sessionVersion)) return
          if (err) {
            this.confirmLoading = false
            return
          }
          const httpurl = model.id ? this.url.edit : this.url.add
          const method = model.id ? 'put' : 'post'
          const formData = Object.assign({}, model, pick(values,'openTime'))
          httpAction(httpurl,formData,method).then((res)=>{
            if (!this.isCurrentSession(sessionVersion)) return
            if (res && res.success === true) {
              this.$message.success(res.message || '保存成功')
              if (context) this.$emit('ok', context)
              else this.$emit('ok')
              if (this.isCurrentSession(sessionVersion)) this.close()
            } else {
              this.$message.warning('保存未成功，请重试。')
            }
          }).catch(() => {
            if (this.isCurrentSession(sessionVersion)) this.$message.warning('未能确认保存结果，请核对课程关系后重试。')
          }).finally(() => {
            if (this.isCurrentSession(sessionVersion)) this.confirmLoading = false
          })
        })
      },
      handleCancel () {
        this.close()
      },
      popupCallback(row){
        this.form.setFieldsValue(pick(row,'openTime'))
      },

      
    }
  }
</script>
