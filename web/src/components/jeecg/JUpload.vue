<template>
  <div :id="containerId" class="j-upload" style="position: relative">

    <!--  ---------------------------- begin 图片左右换位置 ------------------------------------- -->
    <div class="movety-container" :style="{top:top+'px',left:left+'px',display:moveDisplay}" style="padding:0 8px;position: absolute;z-index: 91;height: 32px;width: 104px;text-align: center;">
      <div :id="containerId+'-mover'" :class="showMoverTask?'uploadty-mover-mask':'movety-opt'" style="margin-top: 12px">
        <a @click="moveLast" style="margin: 0 5px;"><a-icon type="arrow-left" style="color: #fff;font-size: 16px"/></a>
        <a @click="moveNext" style="margin: 0 5px;"><a-icon type="arrow-right" style="color: #fff;font-size: 16px"/></a>
      </div>
    </div>
    <!--  ---------------------------- end 图片左右换位置 ------------------------------------- -->

    <a-upload
      name="file"
      :key="session"
      :multiple="multiple"
      :action="getUploadAction()"
      :headers="headers"
      :data="getUploadData"
      :fileList="fileList"
      :beforeUpload="beforeUpload"
      @change="handleChange"
      :disabled="disabled || !active"
      :returnUrl="returnUrl"
      :listType="complistType"
      @preview="handlePreview"
      :class="{'uploadty-disabled':disabled}">
      <template>
        <div v-if="isImageComp">
          <a-icon type="plus" />
          <div class="ant-upload-text">{{ text }}</div>
        </div>
        <a-button v-else-if="fileList.length==0 || buttonVisible">
         <a-icon type="upload" />{{ text }}
        </a-button>
      </template>
    </a-upload>
    <a-modal :visible="previewVisible" :footer="null" @cancel="handleCancel">
      <img alt="example" style="width: 100%" :src="previewImage" />
    </a-modal>
  </div>
</template>

<script>

  import Vue from 'vue'
  import { ACCESS_TOKEN,SYS_CONFIG } from "@/store/mutation-types"
  import {getAction , postAction, deleteAction} from "@/api/manage"
  const FILE_TYPE_ALL = "all"
  const FILE_TYPE_IMG = "image"
  const FILE_TYPE_TXT = "file"

  const UPLOAD_TARGET_LOCAL = "local"
  const UPLOAD_TARGET_QINIU = "qiniu"
  const UPLOAD_TARGET_OSS = "oss"
  const UPLOAD_TARGET_COS = "cos"

  const uidGenerator=()=>{
    return '-'+parseInt(Math.random()*10000+1,10);
  }
  const uuidGenerator=()=>{
    var s = []
    var hexDigits = '0123456789abcdef'
    for (var i = 0; i < 36; i++) {
      s[i] = hexDigits.substr(Math.floor(Math.random() * 0x10), 1)
    }
    s[14] = '4' // bits 12-15 of the time_hi_and_version field to 0010
    s[19] = hexDigits.substr((s[19] & 0x3) | 0x8, 1) // bits 6-7 of the clock_seq_hi_and_reserved to 01
    s[8] = s[13] = s[18] = s[23] = '-'
    var uuid = s.join('')
    uuid = uuid.replace(/-/g,"")
    return uuid
  }
  const getFileName=(path)=>{
    if(path.lastIndexOf("\\")>=0){
      let reg=new RegExp("\\\\","g");
      path = path.replace(reg,"/");
    }
    return path.substring(path.lastIndexOf("/")+1);
  }
  export default {
    name: 'JUpload',
    data(){
      return {
        urlDownload: "",
        downloadUrl:{
          local: this.$store.getters.sysConfig.staticDomain + '/',
          qiniu: this.$store.getters.sysConfig.qiniuDomain + '/'
        },
        uploadAction:{
          local: window._CONFIG['domianURL'] + "/sys/common/upload",
          qiniu: "//upload-" + this.$store.getters.sysConfig.qiniuArea + ".qiniup.com",
          oss: "",
          cos: ""
        },
        tokenAction: {
          qiniu: "/common/qiniu/getToken"
        },
        headers:{},
        fileList: [],
        uploadToken: '',
        uploadKey: {},
        newFileList: [],
        uploadGoOn:true,
        uploadVersion: 0,
        uploadOperations: {},
        confirmedFiles: [],
        uploadState: 'ready',
        previewVisible: false,
        //---------------------------- begin 图片左右换位置 -------------------------------------
        previewImage: '',
        containerId:'',
        top:'',
        left:'',
        moveDisplay:'none',
        showMoverTask:false,
        moverHold:false,
        currentImg:''
        //---------------------------- end 图片左右换位置 -------------------------------------
      }
    },
    props:{
      // A dialog revision invalidates callbacks from a previous editing session.
      session: { type: Number, default: 0 },
      active: { type: Boolean, default: true },
      //按钮文本
      text:{
        type:String,
        required:false,
        default:"点击上传"
      },
      //文件类型
      fileType:{
        type:String,
        required:false,
        default:FILE_TYPE_ALL
      },
      //上传到的路径
      uploadPath: {
        type: String,
        require: false,
        default: ""
      },
      //文件名，不填则自动生成uuid作为文件名
      fileName: {
        type: String,
        require: false
      },
      //最大文件尺寸（MB）
      maxFileSize:{
        type: Number,
        required: false,
        default: 1000
      },
      // 文件上传目标， 默认本地
      uploadTarget:{
        type: String,
        required: false,
        default: Vue.ls.get(SYS_CONFIG).uploadType
      },
      /*这个属性用于控制文件上传的业务路径*/
      bizPath:{
        type:String,
        required:false,
        default:"temp"
      },
      //上传后的文件key
      value:{
        type:String,
        required:false
      },
      // update-begin- --- author:wangshuai ------ date:20190929 ---- for:Jupload组件增加是否能够点击
      disabled:{
        type:Boolean,
        required:false,
        default: false
      },
      //是否支持文件多选
      multiple:{
        type: Boolean,
        required: false,
        default: false
      },
      /**
       * update -- author:lvdandan -- date:20190219 -- for:Jupload组件增加是否返回url，
       * true：仅返回url
       * false：返回fileName filePath fileSize
       */
      returnUrl:{
        type:Boolean,
        required:false,
        default: true
      },
      //最大文件数量，0不限
      number:{
        type:Number,
        required:false,
        default: 0
      },
      //是否自动删除文件
      autoDelete:{
        type:Boolean,
        required:false,
        default: true
      },
      //上传按钮是否显示
      buttonVisible:{
        type:Boolean,
        required:false,
        default: true
      },
    },
    watch:{
      session() { this.invalidateUploads() },
      active(value) { if (!value) this.invalidateUploads() },
      value:{
        immediate: true,
        handler() {
          let val = this.value
          if (val instanceof Array) {
            if(this.returnUrl){
              this.initFileList(val.join(','))
            }else{
              this.initFileListArr(val);
            }
          } else {
            this.initFileList(val)
          }
        }
      }
    },
    computed:{
      isImageComp(){
        return this.fileType === FILE_TYPE_IMG
      },
      complistType(){
        return this.fileType === FILE_TYPE_IMG?'picture-card':'text'
      }
    },
    created(){
      const token = Vue.ls.get(ACCESS_TOKEN);
      this.headers = {"X-Access-Token":token}
      //---------------------------- begin 图片左右换位置 -------------------------------------
      this.containerId = 'container-ty-'+new Date().getTime();
      //---------------------------- end 图片左右换位置 -------------------------------------
    },

    beforeDestroy() {
      this.uploadVersion += 1
    },

    methods:{
      invalidateUploads() {
        this.uploadVersion += 1
        this.uploadOperations = {}
        this.fileList = this.confirmedFiles.slice()
        this.setUploadState()
      },
      isCurrentUpload(operation) {
        return this.active && operation && operation.version === this.uploadVersion &&
          this.uploadOperations[operation.uid] === operation
      },
      setUploadState() {
        const states = Object.keys(this.uploadOperations).map(uid => this.uploadOperations[uid].status)
        this.uploadState = states.includes('uploading') ? 'uploading' :
          states.includes('registering') ? 'registering' : states.includes('error') ? 'error' : 'ready'
        this.$emit('upload-state', { state: this.uploadState, session: this.session })
      },
      uploadFailed(operation, file, message) {
        if (!this.isCurrentUpload(operation)) return
        operation.status = 'error'
        file.status = 'error'
        this.fileList = this.confirmedFiles.concat(file)
        this.setUploadState()
        this.$message.error(message || `${file.name} 上传失败，请重试或移除失败文件。`)
      },
      storageKey(response) {
        const key = this.uploadTarget === UPLOAD_TARGET_QINIU ? response && !response.error && response.success !== false && response.key :
          response && response.success === true && response.message
        // Storage keys are opaque paths, never a human-readable backend error.
        return typeof key === 'string' && key.length > 0 && key.length <= 2048 &&
          !/[\s,\\?#]/.test(key) && !key.startsWith('/') && !key.includes('..') &&
          !/^[a-z][a-z0-9+.-]*:/i.test(key) ? key : null
      },
      //获取上传目标地址
      getUploadAction(){
        switch(this.uploadTarget){
          case UPLOAD_TARGET_LOCAL:
            console.log(this.uploadAction.local);
            return this.uploadAction.local;
          case UPLOAD_TARGET_QINIU:
            console.log(this.uploadAction.qiniu);
            return this.uploadAction.qiniu;
          case UPLOAD_TARGET_OSS:
            return this.uploadAction.oss;
          case UPLOAD_TARGET_COS:
            return this.uploadAction.cos;
          default:
            return this.uploadAction.local
        }
      },
      //获取下载链接
      getDownloadUrl(key){
        console.log(key);
        console.log(this.uploadTarget);
        switch(this.uploadTarget){
          case UPLOAD_TARGET_LOCAL:
            return this.downloadUrl.local + key;
          case UPLOAD_TARGET_QINIU:
            return this.downloadUrl.qiniu + key;
          case UPLOAD_TARGET_OSS:
            return this.downloadUrl.oss + key;
          case UPLOAD_TARGET_COS:
            return this.downloadUrl.cos + key;
          default:
            return this.uploadAction.local + key;
        }
      },
      //获取要上传数据
      getUploadData(file){
        switch(this.uploadTarget){
          case UPLOAD_TARGET_LOCAL:
            return {'isup':1,'bizPath':this.bizPath};
          case UPLOAD_TARGET_QINIU:
            return {'token': this.uploadToken, 'key': this.uploadKey[file.uid]};
          case UPLOAD_TARGET_OSS:
            return {};
          case UPLOAD_TARGET_COS:
            return {};
          default:
            return {'isup':1,'bizPath':this.bizPath};
        } 
      },
      //获取七牛TOKEN
      getQiniuToken(operation){
        return getAction(this.tokenAction.qiniu, {}).then(res => {
          if (!res || res.success !== true || !res.keyPrefix || !res.result) {
            throw new Error('Upload credential unavailable')
          }
          if (!this.isCurrentUpload(operation)) throw new Error('Upload session expired')
          this.uploadToken = res.result
          return res.keyPrefix
        })
      },
      //获取文件key
      getFileFullName(suffix){
        return this.uploadPath + 
        (this.fileName ? this.fileName : uuidGenerator()) + '.' + suffix
      },
      //保存文件记录
      saveToDB: function(fileName, filePath, fileLocation, fileTag){
        return postAction("/system/sysFile/add", { fileName, filePath, fileLocation, fileTag }).then(res => {
          if (!res || res.success !== true || !res.result || typeof res.result.id !== 'string' ||
              !res.result.id || res.result.filePath !== filePath) throw new Error('Upload registration failed')
          return res.result
        })
      },
      //删除文件记录
      delFromBD(filePath){
          return deleteAction("/system/sysFile/deleteByPath", {
            filePath: filePath
          })
      },
      initFileListArr(val){
        if(!val || val.length==0){
          this.fileList = [];
          this.confirmedFiles = [];
          return;
        }
        let fileList = [];
        for(var a=0;a<val.length;a++){
          let url = this.getDownloadUrl(val[a].filePath);
          fileList.push({
            uid:uidGenerator(),
            name:val[a].fileName,
            status: 'done',
            url: url,
            response:{
              status:"history",
              message:val[a].filePath
            }
          })
        }
        this.fileList = fileList
        this.confirmedFiles = fileList.slice()
      },
      //从value生成文件列表
      initFileList(paths){
        if(!paths || paths.length==0){
          //return [];
          // update-begin- --- author:os_chengtgen ------ date:20190729 ---- for:issues:326,Jupload组件初始化bug
          this.fileList = [];
          this.confirmedFiles = [];
          return;
          // update-end- --- author:os_chengtgen ------ date:20190729 ---- for:issues:326,Jupload组件初始化bug
        }
        let fileList = [];
        let arr = paths.split(",")
        for(var a=0;a<arr.length;a++){
          // let url = getFileAccessHttpUrl(arr[a]);
          let url = this.getDownloadUrl(arr[a]);
          console.log(url);
          fileList.push({
            uid:uidGenerator(),
            name:getFileName(arr[a]),
            status: 'done',
            url: url,
            response:{
              status:"history",
              message:arr[a]
            }
          })
        }
        console.log("initFileList")
        console.log(fileList)
        this.fileList = fileList
        this.confirmedFiles = fileList.slice()
      },
      handlePathChange(){
        let uploadFiles = this.fileList
        let path = ''
        if(!uploadFiles || uploadFiles.length==0){
          path = ''
        }
        let arr = [];

        for(var a=0;a<uploadFiles.length;a++){
          // update-begin-author:lvdandan date:20200603 for:【TESTA-514】【开源issue】多个文件同时上传时，控制台报错
          if(uploadFiles[a].status === 'done' && (uploadFiles[a]._uploadReady || uploadFiles[a].response.status === 'history')) {
            arr.push(uploadFiles[a].response.message)
          }else{
            return;
          }
          // update-end-author:lvdandan date:20200603 for:【TESTA-514】【开源issue】多个文件同时上传时，控制台报错
        }
        if(arr.length>0){
          path = arr.join(",")
        }
        this.$emit('change', path);
      },
      //上传之前
      beforeUpload(file){
        if (!this.active || this.disabled) return false
        if (this.fileType === FILE_TYPE_IMG && !file.type.startsWith('image/')) {
          this.$message.warning('请上传图片')
          return false
        }
        if (file.size > this.maxFileSize * 1024 * 1024) {
          this.$message.warning("文件超过" + this.maxFileSize + "MB")
          return false
        }
        // Retrying a failed selection clears only failed operations, not concurrent uploads.
        Object.keys(this.uploadOperations).forEach(uid => {
          if (this.uploadOperations[uid].status === 'error') this.$delete(this.uploadOperations, uid)
        })
        const operation = { uid: file.uid, version: this.uploadVersion, status: 'uploading' }
        this.$set(this.uploadOperations, file.uid, operation)
        this.setUploadState()
        const parts = file.name.split('.')
        const suffix = parts.length > 1 ? parts.pop() : ''
        if (this.uploadTarget === UPLOAD_TARGET_QINIU) {
          return this.getQiniuToken(operation).then(prefix => {
            if (!this.isCurrentUpload(operation)) return Promise.reject(new Error('Upload session expired'))
            this.uploadKey[file.uid] = prefix + uuidGenerator() + (suffix ? '.' + suffix : '')
            this.$emit('selected', this.uploadKey[file.uid], file)
          }).catch(error => {
            this.uploadFailed(operation, file, '无法获取上传凭证，请重试。')
            throw error
          })
        }
        this.uploadKey[file.uid] = this.getFileFullName(suffix)
        this.$emit('selected', this.uploadKey[file.uid], file)
        return true
      },
      async handleChange(info) {
        const file = info.file
        const operation = this.uploadOperations[file.uid]
        if (!this.active) return
        if (file.status === 'removed') {
          // Removing a failed/pending file also invalidates its registration callback.
          if (operation) this.$delete(this.uploadOperations, file.uid)
          const confirmed = this.confirmedFiles.find(item => item.uid === file.uid)
          if (confirmed) this.handleDelete(confirmed)
          this.confirmedFiles = this.confirmedFiles.filter(item => item.uid !== file.uid)
          this.fileList = this.fileList.filter(item => item.uid !== file.uid)
          this.setUploadState()
          this.emitConfirmedFiles()
          return
        }
        if (!this.isCurrentUpload(operation)) return
        if (file.status === 'uploading') {
          this.fileList = info.fileList
          return
        }
        if (file.status === 'error') {
          this.uploadFailed(operation, file)
          return
        }
        if (file.status !== 'done' || operation.status !== 'uploading') return
        const key = this.storageKey(file.response)
        if (!key) {
          this.uploadFailed(operation, file, '文件上传未成功，请重试或移除失败文件。')
          return
        }
        operation.status = 'registering'
        this.setUploadState()
        try {
          const registered = await this.saveToDB(file.name, key, this.uploadTarget === UPLOAD_TARGET_QINIU ? 2 : 1, '后台上传')
          if (!this.isCurrentUpload(operation)) return
          file.response = { ...file.response, message: key }
          file.url = this.getDownloadUrl(key)
          file._uploadReady = true
          operation.status = 'ready'
          const confirmed = this.confirmedFiles.filter(item => item.uid !== file.uid).concat(file)
          // Implicit replacement must not delete the attachment still stored in the course.
          this.confirmedFiles = this.number > 0 ? confirmed.slice(-this.number) : confirmed
          this.fileList = this.confirmedFiles.concat(info.fileList.filter(item => {
            const other = this.uploadOperations[item.uid]
            return other && other.status !== 'ready' && item.uid !== file.uid
          }))
          this.setUploadState()
          this.emitConfirmedFiles()
          this.$emit('saved', registered)
          this.$message.success(`${file.name} 上传成功!`)
        } catch (error) {
          this.uploadFailed(operation, file, '文件登记未成功，请重试或移除失败文件。')
        }
      },
      emitConfirmedFiles() {
        if (this.uploadState !== 'ready') return
        if (this.returnUrl) {
          this.$emit('change', this.confirmedFiles.map(file => file.response.message).join(','))
        } else {
          this.$emit('change', this.confirmedFiles.map(file => ({
            fileName: file.name, filePath: file.response.message, fileSize: file.size
          })))
        }
      },
      handleDelete(file){
        console.log("删除文件");
        if(this.autoDelete){
          this.delFromBD(file.response.message)
        }
        this.$emit('delete', file.response.message)
        console.log(file)
      },
      handlePreview(file){
        if(this.fileType === FILE_TYPE_IMG){
          this.previewImage = file.url || file.thumbUrl;
          this.previewVisible = true;
        }else{
          location.href=file.url
        }
      },
      handleCancel(){
        this.previewVisible = false;
      },
      //---------------------------- begin 图片左右换位置 -------------------------------------
      moveLast(){
        if (this.disabled || this.uploadState !== 'ready') return
        //console.log(ev)
        //console.log(this.fileList)
        //console.log(this.currentImg)
        let index = this.getIndexByUrl();
        if(index==0){
          this.$message.warn('未知的操作')
        }else{
          let curr = this.fileList[index].url;
          let last = this.fileList[index-1].url;
          let arr =[]
          for(let i=0;i<this.fileList.length;i++){
            if(i==index-1){
              arr.push(curr)
            }else if(i==index){
              arr.push(last)
            }else{
              arr.push(this.fileList[i].url)
            }
          }
          this.currentImg = last
          this.$emit('change',arr.join(','))
        }
      },
      moveNext(){
        if (this.disabled || this.uploadState !== 'ready') return
        let index = this.getIndexByUrl();
        if(index==this.fileList.length-1){
          this.$message.warn('已到最后~')
        }else{
          let curr = this.fileList[index].url;
          let next = this.fileList[index+1].url;
          let arr =[]
          for(let i=0;i<this.fileList.length;i++){
            if(i==index+1){
              arr.push(curr)
            }else if(i==index){
              arr.push(next)
            }else{
              arr.push(this.fileList[i].url)
            }
          }
          this.currentImg = next
          this.$emit('change',arr.join(','))
        }
      },
      getIndexByUrl(){
        for(let i=0;i<this.fileList.length;i++){
          if(this.fileList[i].url === this.currentImg || encodeURI(this.fileList[i].url) === this.currentImg){
            return i;
          }
        }
        return -1;
      }
    },
    mounted(){
      const moverObj = document.getElementById(this.containerId+'-mover');
      moverObj.addEventListener('mouseover',()=>{
        this.moverHold = true
        this.moveDisplay = 'block';
      });
      moverObj.addEventListener('mouseout',()=>{
        this.moverHold = false
        this.moveDisplay = 'none';
      });
      let picList = document.getElementById(this.containerId)?document.getElementById(this.containerId).getElementsByClassName('ant-upload-list-picture-card'):[];
      if(picList && picList.length>0){
        picList[0].addEventListener('mouseover',(ev)=>{
          ev = ev || window.event;
          let target = ev.target || ev.srcElement;
          if('ant-upload-list-item-info' == target.className){
            this.showMoverTask=false
            let item = target.parentElement
            this.left = item.offsetLeft
            this.top=item.offsetTop+item.offsetHeight-50;
            this.moveDisplay = 'block';
            this.currentImg = target.getElementsByTagName('img')[0].src
          }

        });

        picList[0].addEventListener('mouseout',(ev)=>{
          ev = ev || window.event;
          let target = ev.target || ev.srcElement;
          //console.log('移除',target)
          if('ant-upload-list-item-info' == target.className){
            this.showMoverTask=true
            setTimeout(()=>{
              if(this.moverHold === false)
                this.moveDisplay = 'none';
            },100)
          }
          if('ant-upload-list-item ant-upload-list-item-done' == target.className || 'ant-upload-list ant-upload-list-picture-card'== target.className){
            this.moveDisplay = 'none';
          }
        })
        //---------------------------- end 图片左右换位置 -------------------------------------
      }
    },
    model: {
      prop: 'value',
      event: 'change'
    }
  }
</script>

<style lang="less">
.j-upload {
.uploadty-disabled{
  .ant-upload-list-item {
    .anticon-close{
      display: none;
    }
    .anticon-delete{
      display: none;
    }
  }
}
  //---------------------------- begin 图片左右换位置 -------------------------------------
  .uploadty-mover-mask{
    background-color: rgba(0, 0, 0, 0.5);
    opacity: .8;
    color: #fff;
    height: 28px;
    line-height: 28px;
  }
  //---------------------------- end 图片左右换位置 -------------------------------------
}
</style>