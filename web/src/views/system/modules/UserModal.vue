<template>
  <a-drawer
    :title="title"
    :maskClosable="true"
    :width="drawerWidth"
    placement="right"
    :closable="true"
    @close="handleCancel"
    :visible="visible"
    style="height: calc(100% - 55px);overflow: auto;padding-bottom: 53px;">

    <template slot="title">
      <div style="width: 100%;">
        <span>{{ title }}</span>
        <span style="display:inline-block;width:calc(100% - 51px);padding-right:10px;text-align: right">
          <a-button @click="toggleScreen" icon="appstore" style="height:20px;width:20px;border:0px"></a-button>
        </span>
      </div>

    </template>

    <a-spin :spinning="confirmLoading || loading">
      <a-alert v-if="loadError || saveError" type="error" show-icon style="margin-bottom: 16px">
        <span slot="message">{{ loadError || saveError }} <a v-if="loadError" @click="loadSessionData()">重试读取</a></span>
      </a-alert>
      <a-form :form="form">

        <a-form-item label="身份" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-radio-group v-model="userIdentity" @change="identityChange">
            <a-radio :value="'1'">学生</a-radio>
            <a-radio :value="'2'">上级</a-radio>
          </a-radio-group>
        </a-form-item>

        <a-form-item label="用户账号" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input placeholder="请输入用户账号" v-decorator.trim="[ 'username', validatorRules.username]" :readOnly="!!model.id"/>
        </a-form-item>

        <template v-if="!model.id">
          <a-form-item label="登陆密码" :labelCol="labelCol" :wrapperCol="wrapperCol" >
            <a-input type="password" placeholder="请输入登陆密码" v-decorator="[ 'password', validatorRules.password]" />
          </a-form-item>

          <a-form-item label="确认密码" :labelCol="labelCol" :wrapperCol="wrapperCol" >
            <a-input type="password" @blur="handleConfirmBlur" placeholder="请重新输入登陆密码" v-decorator="[ 'confirmpassword', validatorRules.confirmpassword]"/>
          </a-form-item>
        </template>

        <a-form-item label="用户姓名" :labelCol="labelCol" :wrapperCol="wrapperCol" >
          <a-input placeholder="请输入用户姓名" v-decorator.trim="[ 'realname', validatorRules.realname]" />
        </a-form-item>

        <a-form-item label="工号" :labelCol="labelCol" :wrapperCol="wrapperCol" v-if="isShow.workNo==true">
          <a-input placeholder="请输入工号" v-decorator="[ 'workNo', validatorRules.workNo]" />
        </a-form-item>

        <a-form-item label="职务" :labelCol="labelCol" :wrapperCol="wrapperCol" v-if="isShow.post==true">
          <j-select-position placeholder="请选择职务" :multiple="false" v-decorator="['post', {}]"/>
        </a-form-item>

        <a-form-item label="学校" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input placeholder="请输入学校" v-decorator="[ 'school']" />
        </a-form-item>

        <a-form-item label="角色分配" :labelCol="labelCol" :wrapperCol="wrapperCol" v-show="!roleDisabled" >
          <a-select
            mode="multiple"
            style="width: 100%"
            placeholder="请选择用户角色"
            optionFilterProp = "children"
            v-model="selectedRole"
            :getPopupContainer= "(target) => target.parentNode">
            <a-select-option v-for="(role,roleindex) in roleList" :key="roleindex.toString()" :value="role.id">
              {{ role.roleName }}
            </a-select-option>
          </a-select>
        </a-form-item>

        <!--部门分配-->
        <a-form-item :label="(isShow.departId?'部门':'班级') + '分配'" :labelCol="labelCol" :wrapperCol="wrapperCol" v-show="!departDisabled">
          <a-input-search
            placeholder="点击选择部门"
            v-model="checkedDepartNameString"
            readOnly
            @search="onSearch">
            <a-button slot="enterButton" icon="search">选择</a-button>
          </a-input-search>
        </a-form-item>

        <a-form-item label="负责部门" :labelCol="labelCol" :wrapperCol="wrapperCol"  v-if="isShow.departId==true">
          <a-select
            mode="multiple"
            style="width: 100%"
            placeholder="请选择负责部门"
            v-model="departIds"
            optionFilterProp = "children"
            :getPopupContainer = "(target) => target.parentNode"
            :dropdownStyle="{maxHeight:'200px',overflow:'auto'}"
          >
            <a-select-option v-for="item in resultDepartOptions" :key="item.key" :value="item.key"
            >{{item.title}}</a-select-option
            >
          </a-select>
        </a-form-item>
        <!-- update--end--autor:wangshuai-----date:20200108------for：新增身份和负责部门------ -->
        <a-form-item v-if="false" label="头像" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-image-upload class="avatar-uploader" text="上传" v-model="fileList" ></j-image-upload>
        </a-form-item>

        <a-form-item label="生日" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-date-picker
            style="width: 100%"
            placeholder="请选择生日"
            v-decorator="['birthday', {initialValue:!model.birthday?null:moment(model.birthday,dateFormat)}]"
            :getCalendarContainer="node => node.parentNode"/>
        </a-form-item>

        <a-form-item label="性别" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-select v-decorator="[ 'sex', {}]" placeholder="请选择性别" :getPopupContainer= "(target) => target.parentNode">
            <a-select-option :value="1">男</a-select-option>
            <a-select-option :value="2">女</a-select-option>
          </a-select>
        </a-form-item>

        <a-form-item label="邮箱" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input placeholder="请输入邮箱" v-decorator="[ 'email', validatorRules.email]" />
        </a-form-item>

        <a-form-item label="手机号码" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input placeholder="请输入手机号码" :disabled="isDisabledAuth('user:form:phone')" v-decorator="[ 'phone', validatorRules.phone]" />
        </a-form-item>

        <a-form-item label="座机" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <a-input placeholder="请输入座机" v-decorator="[ 'telephone', validatorRules.telephone]"/>
        </a-form-item>

        <a-form-item v-if="false" label="工作流引擎" :labelCol="labelCol" :wrapperCol="wrapperCol">
          <j-dict-select-tag  v-decorator="['activitiSync', {}]" placeholder="请选择是否同步工作流引擎" :type="'radio'" :triggerChange="true" dictCode="activiti_sync"/>
        </a-form-item>

      </a-form>
    </a-spin>
    <depart-window :key="sessionVersion" ref="departWindow" @ok="modalFormOk"></depart-window>

    <div class="drawer-bootom-button" v-show="!disableSubmit">
      <a-button @click="confirmCancel" style="margin-right: .8rem">取消</a-button>
      <a-button @click="handleSubmit" :disabled="loading || !!loadError" type="primary" :loading="confirmLoading">提交</a-button>
    </div>
  </a-drawer>
</template>

<script>
  import pick from 'lodash.pick'
  import moment from 'moment'
  import Vue from 'vue'
  // 引入搜索部门弹出框的组件
  import departWindow from './DepartWindow'
  import JSelectPosition from '@/components/jeecgbiz/JSelectPosition'
  import { ACCESS_TOKEN } from "@/store/mutation-types"
  import { getAction } from '@/api/manage'
  import {addUser,editUser,queryUserRole,queryMySubRole } from '@/api/api'
  import { disabledAuthFilter } from "@/utils/authFilter"
  import {duplicateCheck } from '@/api/api'
  import JImageUpload from '../../../components/jeecg/JImageUpload'

  export default {
    name: "UserModal",
    components: {
      JImageUpload,
      departWindow,
      JSelectPosition
    },
    data () {
      return {
        departDisabled: false, //是否是我的部门调用该页面
        roleDisabled: false, //是否是角色维护调用该页面
        modalWidth:800,
        drawerWidth:700,
        modaltoggleFlag:true,
        confirmDirty: false,
        selectedDepartKeys:[], //保存用户选择部门id
        checkedDepartKeys:[],
        checkedDepartNames:[], // 保存部门的名称 =>title
        checkedDepartNameString:"", // 保存部门的名称 =>title
        resultDepartOptions:[],
        userId:"", //保存用户id
        disableSubmit:false,
        userDepartModel:{userId:'',departIdList:[]}, // 保存SysUserDepart的用户部门中间表数据需要的对象
        dateFormat:"YYYY-MM-DD",
        validatorRules:{
          username:{
            rules: [{
              required: true, message: '请输入用户账号!'
            },{
              validator: this.validateUsername,
            }]
          },
          password:{
            rules: [{
              required: true,
              pattern:/^[\w]{6,}$/,
              message: '密码由6位以上数字、大小写字母和特殊符号组成!'
            }, {
              validator: this.validateToNextPassword,
            }],
          },
          confirmpassword:{
            rules: [{
              required: true, message: '请重新输入登陆密码!',
            }, {
              validator: this.compareToFirstPassword,
            }],
          },
          realname:{rules: [{ required: true, message: '请输入用户名称!' }]},
          phone:{rules: [{validator: this.validatePhone}]},
          email:{
            rules: [{
              validator: this.validateEmail
            }],
          },
          roles:{},
          //  sex:{initialValue:((!this.model.sex)?"": (this.model.sex+""))}
          workNo: {
            rules: [
              { validator: this.validateWorkNo }
            ]
          },
          telephone: {
            rules: [
              { pattern: /^0\d{2,3}-[1-9]\d{6,7}$/, message: '请输入正确的座机号码' },
            ]
          }
        },
        isShow:{
          departId:false,
          workNo:false,
          post:false,
        },
        departIds:[], //负责部门id
        title:"操作",
        visible: false,
        model: {},
        roleList:[],
        selectedRole:[],
        labelCol: {
          xs: { span: 24 },
          sm: { span: 5 },
        },
        wrapperCol: {
          xs: { span: 24 },
          sm: { span: 16 },
        },
        uploadLoading:false,
        confirmLoading: false,
        loading: false,
        sessionVersion: 0,
        loadRequestId: 0,
        editContext: null,
        cancelPrompt: null,
        departWindowVersion: 0,
        loadError: '',
        saveError: '',
        headers:{},
        form:this.$form.createForm(this),
        picUrl: "",
        url: {
          fileUpload: window._CONFIG['domianURL']+"/sys/common/upload",
          userWithDepart: "/sys/user/userDepartList", // 引入为指定用户查看部门信息需要的url
          userId:"/sys/user/generateUserId", // 引入生成添加用户情况下的url
          syncUserByUserName:"/process/extActProcess/doSyncUserByUserName",//同步用户到工作流
        },
        userIdentity: '1',
        fileList:[],
      }
    },
    created () {
      const token = Vue.ls.get(ACCESS_TOKEN);
      this.headers = {"X-Access-Token":token}

    },
    beforeDestroy () { this.close() },
    computed:{
      uploadAction:function () {
        return this.url.fileUpload;
      }
    },
    methods: {
      isDisabledAuth(code){
        return disabledAuthFilter(code);
      },
      //窗口最大化切换
      toggleScreen(){
        if(this.modaltoggleFlag){
          this.modalWidth = window.innerWidth;
        }else{
          this.modalWidth = 800;
        }
        this.modaltoggleFlag = !this.modaltoggleFlag;
      },
      isCurrentSession(version) {
        return this.visible && version === this.sessionVersion && (!this.editContext || !this.editContext.isCurrent || this.editContext.isCurrent())
      },
      isCurrentRead(version, requestId) { return this.isCurrentSession(version) && requestId === this.loadRequestId },
      initialRoleList(version = this.sessionVersion, requestId = this.loadRequestId) {
        return queryMySubRole().then(res => {
          if (!this.isCurrentRead(version, requestId)) return false
          if (!res || res.success !== true || !Array.isArray(res.result) || !res.result.every(row => row && typeof row.id === 'string' && row.id)) return false
          this.roleList = res.result
          if (!this.model.id && !this.roleDisabled && this.userIdentity === '1') this.selectedRole = this.roleList.filter(role => role.roleCode === 'student' || role.roleName === '学生').map(role => role.id)
          return true
        }).catch(() => false)
      },
      loadUserRoles(userid, version = this.sessionVersion, requestId = this.loadRequestId) {
        if (!userid) return Promise.resolve(true)
        return queryUserRole({ userid }).then(res => {
          if (!this.isCurrentRead(version, requestId)) return false
          if (!res || res.success !== true || !Array.isArray(res.result) || !res.result.every(id => typeof id === 'string' && id)) return false
          this.selectedRole = res.result.slice()
          return true
        }).catch(() => false)
      },
      loadSessionData() {
        const version = this.sessionVersion
        if (!this.isCurrentSession(version)) return
        const requestId = ++this.loadRequestId
        const userId = this.userId
        this.loading = true
        this.loadError = ''
        return Promise.all([this.initialRoleList(version, requestId), this.loadUserRoles(userId, version, requestId), this.loadCheckedDeparts(version, requestId)]).then(results => {
          if (this.isCurrentRead(version, requestId) && !results.every(Boolean)) this.loadError = '用户的角色或班级信息读取未完成，请重试后保存。'
        }).finally(() => { if (this.isCurrentRead(version, requestId)) this.loading = false })
      },
      refresh () {
          this.selectedDepartKeys=[];
          this.checkedDepartKeys=[];
          this.checkedDepartNames=[];
          this.checkedDepartNameString = "";
          this.userId=""
          this.resultDepartOptions=[];
          this.departId=[];
          this.changeIdentity("1")
      },
      add (context) {
        const departs = context ? [context.deptId] : (this.departDisabled && Array.isArray(this.userDepartModel.departIdList) ? this.userDepartModel.departIdList.slice() : [])
        const roles = this.roleDisabled ? this.selectedRole.slice() : []
        this.picUrl = ''
        this.refresh()
        this.userDepartModel = { userId: '', departIdList: departs }
        this.selectedRole = roles
        return this.edit({ activitiSync: '1', userIdentity: '1' }, context)
      },
      edit (record, context) {
        const version = ++this.sessionVersion
        this.loadRequestId++
        this.editContext = context ? Object.assign({}, context) : null
        this.confirmLoading = false
        this.cancelPrompt = null
        this.departWindowVersion = 0
        this.loadError = ''
        this.saveError = ''
        this.resetScreenSize()
        this.checkedDepartNameString = ''
        this.checkedDepartNames = []
        this.checkedDepartKeys = []
        this.selectedDepartKeys = []
        this.resultDepartOptions = []
        this.departIds = []
        this.roleList = []
        if (record.id) { this.selectedRole = []; this.userDepartModel = { userId: record.id, departIdList: [] } }
        this.form.resetFields()
        this.userId = record.id || ''
        this.model = Object.assign({}, record)
        this.fileList = record.avatar || []
        this.visible = true
        this.changeIdentity(this.model.userIdentity, true)
        this.$nextTick(() => {
          if (!this.isCurrentSession(version)) return
          const fields = ['username', 'sex', 'realname', 'email', 'phone', 'telephone', 'school']
          if (this.isShow.workNo) fields.push('workNo')
          if (this.isShow.post) fields.push('post')
          this.form.setFieldsValue(pick(this.model, ...fields))
        })
        return this.loadSessionData()
      },
      changeIdentity(userIdentity, preserveRoles){
        if(userIdentity=="2"){
            this.userIdentity="2";
            this.isShow = {
              departId:true,
              workNo:true,
              post:true
            }
            if (!preserveRoles) this.selectedRole = []
        }else{
            this.userIdentity="1";
            this.isShow = {
              departId:false,
              workNo:false,
              post:false
            }
            //查找学生角色
            if (!preserveRoles) this.selectedRole = this.roleList.filter(role=>{
              if(role.roleCode == "student" || role.roleName == "学生"){
                return role
              }
            }).map(role=>{
              return role.id
            })
            console.log(this.selectedRole);
            
        }
      },
      //
      loadCheckedDeparts(version = this.sessionVersion, requestId = this.loadRequestId) {
        if (!this.userId) return Promise.resolve(true)
        const userId = this.userId
        return getAction(this.url.userWithDepart, { userId }).then(res => {
          if (!this.isCurrentRead(version, requestId) || userId !== this.userId) return false
          if (!res || res.success !== true || !Array.isArray(res.result) || !res.result.every(row => row && typeof row.key === 'string' && row.key)) return false
          this.checkedDepartNames = res.result.map(row => row.title)
          this.checkedDepartNameString = this.checkedDepartNames.join(',')
          this.checkedDepartKeys = res.result.map(row => row.key)
          this.resultDepartOptions = res.result.map(row => ({ key: row.key, title: row.title }))
          this.departIds = this.model.departIds ? this.model.departIds.split(',') : this.checkedDepartKeys.slice()
          this.userDepartModel = { userId, departIdList: this.checkedDepartKeys.slice() }
          return true
        }).catch(() => false)
      },
      close () {
        this.sessionVersion++
        this.loadRequestId++
        this.editContext = null
        this.confirmLoading = false
        this.loading = false
        this.cancelPrompt = null
        this.departWindowVersion = 0
        this.form.resetFields()
        if (this.$refs.departWindow && this.$refs.departWindow.visible) this.$refs.departWindow.close()
        this.$emit('close');
        this.visible = false;
        this.disableSubmit = false;
        this.selectedRole = [];
        this.userDepartModel = {userId:'',departIdList:[]};
        this.checkedDepartNames = [];
        this.checkedDepartNameString='';
        this.checkedDepartKeys = [];
        this.selectedDepartKeys = [];
        this.resultDepartOptions=[];
        this.departIds=[];
        this.roleList=[];
        this.changeIdentity("1")
        this.userIdentity="1";
        this.fileList=[];
      },
      moment,
      confirmCancel() {
        if (!this.visible || this.cancelPrompt) return
        const prompt = { version: this.sessionVersion }
        this.cancelPrompt = prompt
        this.$confirm({ title: '确定放弃编辑？',
          onOk: () => { if (this.cancelPrompt === prompt && this.isCurrentSession(prompt.version)) this.close() },
          onCancel: () => { if (this.cancelPrompt === prompt) this.cancelPrompt = null }
        })
      },
      handleSubmit () {
        const version = this.sessionVersion
        if (!this.isCurrentSession(version) || this.disableSubmit || this.loading || this.loadError || this.confirmLoading) return
        const context = this.editContext ? Object.assign({}, this.editContext) : null
        const model = Object.assign({}, this.model)
        const roleIds = this.selectedRole.slice()
        const departIdList = context && !model.id ? [context.deptId] : this.userDepartModel.departIdList.slice()
        const responsibleIds = this.departIds.slice()
        const userIdentity = this.userIdentity, userId = this.userId
        const avatar = Array.isArray(this.fileList) ? this.fileList.slice() : this.fileList
        this.confirmLoading = true
        this.saveError = ''
        this.form.validateFields((err, values) => {
          if (!this.isCurrentSession(version)) return
          if (err) { this.confirmLoading = false; return }
          if (!roleIds.length || !departIdList.length) {
            this.$message.warning(!roleIds.length ? '请选择角色' : '请选择班级')
            this.confirmLoading = false
            return
          }
          const formData = Object.assign({}, model, values)
          formData.id = model.id || userId
          formData.birthday = values.birthday ? (typeof values.birthday.format === 'function' ? values.birthday.format(this.dateFormat) : values.birthday) : ''
          formData.avatar = avatar && avatar.length ? avatar : null
          formData.selectedroles = roleIds.join(',')
          formData.selecteddeparts = departIdList.join(',')
          formData.userIdentity = userIdentity
          formData.departIds = userIdentity === '2' ? responsibleIds.join(',') : ''
          const request = model.id ? editUser : addUser
          request(formData).then(res => {
            if (!this.isCurrentSession(version)) return
            if (res && res.success === true) {
              this.$message.success(res.message || '用户已保存')
              if (context) this.$emit('ok', context)
              else this.$emit('ok')
              if (this.isCurrentSession(version)) this.close()
            } else this.saveError = '用户未保存成功，填写内容已保留，请重试。'
          }).catch(() => { if (this.isCurrentSession(version)) this.saveError = '未能确认保存结果，请核对用户列表后重试。' })
            .finally(() => { if (this.isCurrentSession(version)) this.confirmLoading = false })
        })
      },
      handleCancel () {
        this.close()
      },
      validateToNextPassword  (rule, value, callback) {
        const form = this.form;
        const confirmpassword=form.getFieldValue('confirmpassword');

        if (value && confirmpassword && value !== confirmpassword) {
          callback('两次输入的密码不一样！');
        }
        if (value && this.confirmDirty) {
          form.validateFields(['confirm'], { force: true })
        }
        callback();
      },
      compareToFirstPassword  (rule, value, callback) {
        const form = this.form;
        if (value && value !== form.getFieldValue('password')) {
          callback('两次输入的密码不一样！');
        } else {
          callback()
        }
      },
      validateDuplicate(params, message, callback) {
        const version = this.sessionVersion
        if (!params.fieldVal) { callback(); return Promise.resolve() }
        return duplicateCheck(params).then(res => {
          if (!this.isCurrentSession(version)) return
          if (res && res.success === true) callback()
          else callback(res && res.code !== 500 ? res.message || '验证未完成，请重试。' : message)
        }).catch(() => { if (this.isCurrentSession(version)) callback('验证未完成，请重试。') })
      },
      validatePhone(rule, value, callback){
        if(!value){
          callback()
        }else{
          //update-begin--Author:kangxiaolin  Date:20190826 for：[05] 手机号不支持199号码段--------------------
          if(new RegExp(/^1[3|4|5|7|8|9][0-9]\d{8}$/).test(value)){
            //update-end--Author:kangxiaolin  Date:20190826 for：[05] 手机号不支持199号码段--------------------

            var params = {
              purpose: 'user_phone',
              fieldVal: value,
              dataId: this.userId
            };
            this.validateDuplicate(params, '手机号已存在!', callback)
          }else{
            callback("请输入正确格式的手机号码!");
          }
        }
      },
      validateEmail(rule, value, callback){
        if(!value){
          callback()
        }else{
          if(new RegExp(/^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/).test(value)){
            var params = {
              purpose: 'user_email',
              fieldVal: value,
              dataId: this.userId
            };
            this.validateDuplicate(params, '邮箱已存在!', callback)
          }else{
            callback("请输入正确格式的邮箱!")
          }
        }
      },
      validateUsername(rule, value, callback){
        var params = {
          purpose: 'user_username',
          fieldVal: value,
          dataId: this.userId
        };
        this.validateDuplicate(params, '用户名已存在!', callback)
      },
      validateWorkNo(rule, value, callback){
        var params = {
          purpose: 'user_work_no',
          fieldVal: value,
          dataId: this.userId
        };
        this.validateDuplicate(params, '工号已存在!', callback)
      },
      handleConfirmBlur  (e) {
        const value = e.target.value;
        this.confirmDirty = this.confirmDirty || !!value
      },

      normFile  (e) {
        console.log('Upload event:', e);
        if (Array.isArray(e)) {
          return e
        }
        return e && e.fileList
      },
      beforeUpload: function(file){
        var fileType = file.type;
        if(fileType.indexOf('image')<0){
          this.$message.warning('请上传图片');
          return false;
        }
        //TODO 验证文件大小
      },
      handleChange (info) {
        this.picUrl = "";
        if (info.file.status === 'uploading') {
          this.uploadLoading = true;
          return
        }
        if (info.file.status === 'done') {
          var response = info.file.response;
          this.uploadLoading = false;
          console.log(response);
          if(response.success){
            this.model.avatar = response.message;
            this.picUrl = "Has no pic url yet";
          }else{
            this.$message.warning(response.message);
          }
        }
      },
      // 搜索用户对应的部门API
      onSearch(){
        if (!this.visible || this.departDisabled || this.confirmLoading) return
        this.departWindowVersion = this.sessionVersion
        this.$refs.departWindow.add(this.checkedDepartKeys,this.userId);
      },

      // 获取用户对应部门弹出框提交给返回的数据
      modalFormOk (formData) {
        if (!this.visible || this.departDisabled || this.departWindowVersion !== this.sessionVersion) return
        this.checkedDepartNames = [];
        this.selectedDepartKeys = [];
        this.checkedDepartNameString = '';
        this.userId = formData.userId;
        this.userDepartModel.userId = formData.userId;
        this.departIds=[];
        this.resultDepartOptions=[];
        var depart=[];
        for (let i = 0; i < formData.departIdList.length; i++) {
          this.selectedDepartKeys.push(formData.departIdList[i].key);
          this.checkedDepartNames.push(formData.departIdList[i].title);
          this.checkedDepartNameString = this.checkedDepartNames.join(",");
          //新增部门选择，如果上面部门选择后不为空直接付给负责部门
          depart.push({
              key:formData.departIdList[i].key,
              title:formData.departIdList[i].title
          })
          this.departIds.push(formData.departIdList[i].key)
        }
        this.resultDepartOptions=depart;
        this.userDepartModel.departIdList = this.selectedDepartKeys;
        this.checkedDepartKeys = this.selectedDepartKeys  //更新当前的选择keys
       },
      // 根据屏幕变化,设置抽屉尺寸
      resetScreenSize(){
        let screenWidth = document.body.clientWidth;
        if(screenWidth < 500){
          this.drawerWidth = screenWidth;
        }else{
          this.drawerWidth = 700;
        }
      },
      identityChange(e){
        this.changeIdentity(e.target.value)
      }
    }
  }
</script>

<style scoped>
  .avatar-uploader > .ant-upload {
    width:104px;
    height:104px;
  }
  .ant-upload-select-picture-card i {
    font-size: 49px;
    color: #999;
  }

  .ant-upload-select-picture-card .ant-upload-text {
    margin-top: 8px;
    color: #666;
  }

  .ant-table-tbody .ant-table-row td{
    padding-top:10px;
    padding-bottom:10px;
  }

  .drawer-bootom-button {
    position: absolute;
    bottom: -8px;
    width: 100%;
    border-top: 1px solid #e8e8e8;
    padding: 10px 16px;
    text-align: right;
    left: 0;
    background: #fff;
    border-radius: 0 0 2px 2px;
  }
</style>
