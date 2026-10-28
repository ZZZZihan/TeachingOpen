<template>
  <j-modal
    :title="title"
    :width="width"
    :visible="visible"
    :confirmLoading="confirmLoading"
    :maskClosable="false"
    :keyboard="!confirmLoading"
    :closable="!confirmLoading"
    :okButtonProps="{ props: { disabled: confirmLoading || !uploadsReady } }"
    :cancelButtonProps="{ props: { disabled: confirmLoading } }"
    switchFullscreen
    @ok="handleOk"
    @cancel="handleCancel"
    cancelText="关闭">
    <a-alert v-if="saveError" ref="saveAlert" tabindex="-1" type="error" :message="saveError" show-icon role="alert" />
    <a-spin :spinning="confirmLoading">
      <div :inert="confirmLoading ? '' : null" :aria-busy="confirmLoading">
      <a-form :form="form">
        <a-form-item label="状态" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-dict-select-tag type="radio" v-decorator="['status',{rules: [{required: true, message: '请选择状态!'}]}]" :trigger-change="true" dictCode="additional_work_status" placeholder="请选择状态"/>
        </a-form-item>
        <a-form-item label="作业类型" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-dict-select-tag type="list" v-decorator="['codeType']" :trigger-change="true" dictCode="work_type" placeholder="请选择作业类型"/>
        </a-form-item>
        <a-form-item label="作业名" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input v-decorator="['workName',{rules: [{required: true, message: '请输入作业名!'}]}]" placeholder="请输入作业名"></a-input>
        </a-form-item>
        <a-form-item label="作业描述" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-textarea v-decorator="['workDesc']" rows="4" placeholder="请输入作业描述"/>
        </a-form-item>
        <a-form-item label="作业封面" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-upload v-decorator="['workCover']" :number="1" :fileType="'image'" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('workCover', $event)"></j-upload>
        </a-form-item>
        <a-form-item label="作业资料" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-upload v-decorator="['workDocumentUrl']" :number="1" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('workDocumentUrl', $event)"></j-upload>
        </a-form-item>
        <a-form-item label="作业文件" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-upload v-decorator="['workUrl']" :number="1" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('workUrl', $event)"></j-upload>
        </a-form-item>
        <a-form-item label="分配班级" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-select-depart :onlyLeaf="true" :onlyCategory="3" :rootOpened="true" :multi="true" v-decorator="['workDept',{rules: [{required: true, message: '请选择班级!'}]}]"/>
        </a-form-item>
        
      </a-form>
      </div>
    </a-spin>
  </j-modal>
</template>

<script>

  import CourseFormRecovery from '@/mixins/CourseFormRecovery'
  import pick from 'lodash/pick'
  import JUpload from '@/components/jeecg/JUpload'
  import JSelectDepart from '@/components/jeecgbiz/JSelectDepart'


  export default {
    name: "TeachingAdditionalWorkModal",
    mixins: [CourseFormRecovery],
    components: { 
      JUpload,
      JSelectDepart,
    },
    data () {
      return {
        form: this.$form.createForm(this),
        title:"操作",
        width:800,
        visible: false,
        model: {},
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
        },
        url: {
          add: "/teaching/teachingAdditionalWork/add",
          edit: "/teaching/teachingAdditionalWork/edit",
        }
      }
    },
    created () {
    },
    methods: {
      add () {
        this.edit({});
      },
      edit (record) {
        if (!this.beginEdit(record)) return
        const version = this.saveVersion
        this.$nextTick(() => {
          if (!this.visible || version !== this.saveVersion) return
          this.form.setFieldsValue(pick(this.model,'codeType','createTime','workName','workDesc','workCover','workDocumentUrl', 'workUrl','workDept','status'))
        })
      },
      popupCallback(row){
        this.form.setFieldsValue(pick(row,'codeType', 'createTime','workName','workDesc','workCover','workDocumentUrl','workUrl','workDept','workIntegral','status'))
      },

      
    }
  }
</script>