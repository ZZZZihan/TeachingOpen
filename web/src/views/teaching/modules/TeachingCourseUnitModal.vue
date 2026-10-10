<template>
  <j-modal
    class="course-resource-dialog"
    :title="title"
    :width="width"
    :confirmLoading="confirmLoading"
    :maskClosable="false"
    :keyboard="!confirmLoading"
    :closable="!confirmLoading"
    :okButtonProps="{ props: { disabled: confirmLoading || !uploadsReady } }"
    :cancelButtonProps="{ props: { disabled: confirmLoading } }"
    okText="保存"
    switchFullscreen
    @ok="handleOk"
    @cancel="handleCancel"
    :visible="visible">
    <a-alert
      v-if="saveError"
      ref="saveAlert"
      tabindex="-1"
      class="course-save-error"
      type="error"
      :message="saveError"
      show-icon
      role="alert" />
    <a-spin :spinning="confirmLoading" tip="正在保存，请稍候…">
      <div :inert="confirmLoading ? '' : null" :aria-busy="confirmLoading">
        <a-form :form="form">
          <a-form-item label="展示排序" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <a-input-number v-decorator="[ 'orderNum']" placeholder="请输入排序"></a-input-number>
          </a-form-item>
          <a-form-item label="所属课程包" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <a-select v-decorator="['courseId', validatorRules.courseId]" rows="4">
              <a-select-option v-for="(course,index) in courseList" :key="index.toString()" :value="course.id">{{ course.courseName }}</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="单元名称" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <a-input v-decorator="[ 'unitName', validatorRules.unitName]" placeholder="请输入单元名称"></a-input>
          </a-form-item>
          <a-form-item label="单元简介" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <a-textarea v-decorator="[ 'unitIntro', validatorRules.unitIntro]" placeholder="请输入单元简介"></a-textarea>
          </a-form-item>
          <a-form-item label="课程封面" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <j-upload v-decorator="['unitCover', validatorRules.unitCover]" :number="1" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('unitCover', $event)"></j-upload>
          </a-form-item>
          <a-form-item label="课程视频" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <a-card>
              <a-radio-group name="courseVideoSource" :defaultValue="1" v-model="model.courseVideoSource" @change="onCourseVideoSourceChange">
                <a-radio :value="1">上传</a-radio>
                <a-radio :value="2">链接</a-radio>
                <a-radio :value="3">外部</a-radio>
              </a-radio-group>
              <a-divider></a-divider>
              <j-upload v-if="model.courseVideoSource==1" v-decorator="['courseVideo', validatorRules.courseVideo]" :number="1" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('courseVideo', $event)"></j-upload>
              <a-input v-if="model.courseVideoSource==2" v-decorator="[ 'courseVideo', validatorRules.courseVideo]" placeholder="请输入视频地址"></a-input>
              <a-textarea v-if="model.courseVideoSource==3" v-decorator="['courseVideo']" placeholder="请输入外部播放器代码"></a-textarea>
            </a-card>
            <a-switch checkedChildren="对学生显示" unCheckedChildren="对学生隐藏" v-model="model.showCourseVideo" defaultChecked/>
          </a-form-item>
          <a-form-item label="课程案例" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <j-upload v-decorator="['courseCase', validatorRules.courseCase]" :number="1" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('courseCase', $event)"></j-upload>
            <a-switch checkedChildren="对学生显示" unCheckedChildren="对学生隐藏" v-model="model.showCourseCase" defaultChecked/>
          </a-form-item>
          <a-form-item label="课程资料" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <j-upload v-decorator="['coursePpt', validatorRules.coursePpt]" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('coursePpt', $event)"></j-upload>
            <a-switch checkedChildren="对学生显示" unCheckedChildren="对学生隐藏" v-model="model.showCoursePpt" />
          </a-form-item>
          <a-form-item label="课程教案" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <j-upload v-decorator="['coursePlan', validatorRules.coursePlan]" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('coursePlan', $event)"></j-upload>
            <a-switch checkedChildren="对学生显示" unCheckedChildren="对学生隐藏" v-model="model.showCoursePlan" />
          </a-form-item>
          <a-form-item label="作业类型" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <j-dict-select-tag type="list" v-decorator="['courseWorkType', {initialValue: 2}, validatorRules.courseWorkType]" :trigger-change="true" dictCode="work_type" placeholder="请选择作业类型"/>
          </a-form-item>
          <a-form-item label="预设作业" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <j-upload v-decorator="['courseWork', validatorRules.courseWork]" :number="1" :trigger-change="true" :session="uploadSession" :active="visible" :disabled="confirmLoading" @upload-state="onUploadState('courseWork', $event)"></j-upload>
          </a-form-item>
          <a-form-item label="课程内容" :labelCol="labelCol" :wrapperCol="wrapperCol" >
            <j-editor v-decorator="['mediaContent', { trigger: 'input' }]" />
          </a-form-item>
          <a-form-item label="地图坐标" :labelCol="labelCol" :wrapperCol="wrapperCol">
            <p>坐标由地图编辑器保存；新建单元或更换所属课程后，请先保存单元。</p>
            <a-row>
              <a-col :span="8">
                <a-form-item label="X" :labelCol="labelCol" :wrapperCol="wrapperCol">
                  <a-input-number v-decorator="['mapX', validatorRules.mapX]" disabled placeholder="请输入地图X坐标" />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="Y" :labelCol="labelCol" :wrapperCol="wrapperCol">
                  <a-input-number v-decorator="['mapY', validatorRules.mapY]" disabled placeholder="请输入地图Y坐标" />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-button type="primary" @click="showMapEdit">地图编辑器</a-button>
              </a-col>
            </a-row>
          </a-form-item>
        </a-form>
      </div>
    </a-spin>
    <!-- <div class="drawer-footer">
      <a-button type="primary" @click="handleOk">确定</a-button>
      <a-button type="default" @click="handleCancel">取消</a-button>
    </div> -->
    <TeachingMapEditor ref="mapEditor" @saved="onMapSaved" />
  </j-modal>
</template>

<script>

import { getAction } from '@/api/manage'
import CourseFormRecovery from '@/mixins/CourseFormRecovery'
import pick from 'lodash.pick'
import JUpload from '@/components/jeecg/JUpload'
import JEditor from '@/components/jeecg/JEditor'
import JDictSelectTag from '@/components/dict/JDictSelectTag'
import TeachingMapEditor from './TeachingMapEditor'
export default {
    name: 'TeachingCourseUnitModal',
    mixins: [CourseFormRecovery],
    components: {
        JUpload,
        JEditor,
        JDictSelectTag,
        TeachingMapEditor
    },
    data () {
        return {
            form: this.$form.createForm(this),
            title: '操作',
            width: 1000,
            visible: false,
            model: {},
            labelCol: {
                xs: { span: 24 },
                sm: { span: 5 }
            },
            wrapperCol: {
                xs: { span: 24 },
                sm: { span: 16 }
            },
            confirmLoading: false,
            validatorRules: {
                unitName: { rules: [
                    { required: true, message: '请输入单元名称!' }
                ] },
                unitIntro: { rules: [
                ] },
                unitCover: {},
                courseId: { rules: [
                    { required: true, message: '请选择所属课程!' }
                ] },
                courseVideo: { rules: [
                ] },
                courseCase: { rules: [
                ] },
                coursePpt: { rules: [
                ] },
                courseWorkType: { rules: [
                    // {required: true, message: '请选择作业类型'}
                ] },
                courseWork: { rules: [
                ] },
                courseWorkAnswer: { rules: [
                ] },
                coursePlan: { rules: [
                ] },
                mapX: { rules: [
                    { pattern: /^-?\d+$/, message: '请输入整数!' }
                ] },
                mapY: { rules: [
                    { pattern: /^-?\d+$/, message: '请输入整数!' }
                ] }
            },
            courseList: [],
            url: {
                add: '/teaching/teachingCourseUnit/add',
                edit: '/teaching/teachingCourseUnit/edit',
                courseList: '/teaching/teachingCourse/list'
            }
        }
    },
    created () {
        this.initCourseList()
    },
    methods: {
        async initCourseList () {
            const courses = []
            try {
                let pageNo = 1
                let total = 0
                do {
                    const res = await getAction(this.url.courseList, { pageNo, pageSize: 100 })
                    if (!res || res.success !== true || !res.result || !Array.isArray(res.result.records)) throw new Error('Course list unavailable')
                    total = Number(res.result.total)
                    if (!Number.isSafeInteger(total) || total < 0 || (!res.result.records.length && courses.length < total)) throw new Error('Incomplete course list')
                    courses.push(...res.result.records)
                    pageNo += 1
                } while (courses.length < total)
                if (!this._isDestroyed) this.courseList = courses
            } catch (error) {
                if (!this._isDestroyed) this.$message.warning('课程列表获取未成功，请重新打开页面后重试。')
            }
        },
        add () {
            this.edit({
                showCourseVideo: true,
                showCourseCase: true,
                showCoursePpt: false,
                showCoursePlan: false
            })
        },
        edit (record) {
            if (!this.beginEdit(record)) return
            const version = this.saveVersion
            this.$nextTick(() => {
                if (version !== this.saveVersion || !this.visible) return
                this.form.setFieldsValue(pick(this.model,
                    'createBy', 'createTime', 'unitName', 'unitIntro', 'courseId', 'unitCover',
                    'courseVideo', 'showCourseVideo', 'courseVideoSource', 'coursePpt', 'showCoursePpt',
                    'courseWorkType', 'courseWork', 'courseWorkAnswer', 'coursePlan', 'showCoursePlan',
                    'courseCase', 'showCourseCase', 'mapX', 'mapY', 'mediaContent', 'orderNum'))
            })
        },
        onCourseVideoSourceChange (v) {
            this.$delete(this.uploadStates, 'courseVideo')
            this.form.setFieldsValue({ courseVideo: '', courseVideoExtern: '' })
            this.model.courseVideoExtern = ''
            this.model.courseVideo = ''
            this.model.courseVideoSource = v.target.value
        },
        popupCallback (row) {
            this.form.setFieldsValue(pick(row,
                'createBy', 'createTime', 'unitName', 'unitIntro', 'courseId',
                'courseVideo', 'showCourseVideo', 'coursePpt', 'showCoursePpt',
                'courseWorkType', 'courseWork', 'courseWorkAnswer', 'orderNum',
                'coursePlan', 'showCoursePlan', 'courseCase', 'showCourseCase', 'mapX', 'mapY'))
        },
        // 显示地图编辑器
        showMapEdit () {
            if (this.confirmLoading) return
            const courseId = this.form.getFieldValue('courseId')
            if (!this.model.id || !courseId || courseId !== this.model.courseId) {
                this.$message.warning('请先保存单元及所属课程，再打开地图编辑器。')
                return
            }
            this.$refs.mapEditor.openById(courseId, this.model.id)
        },
        onMapSaved (result) {
            const courseId = this.form.getFieldValue('courseId')
            if (!this.visible || !result || result.courseId !== this.model.courseId || result.courseId !== courseId) return
            const unit = result.units.find(position => position.id === this.model.id)
            if (!unit) return
            this.model.mapX = unit.mapX
            this.model.mapY = unit.mapY
            this.form.setFieldsValue({ mapX: unit.mapX, mapY: unit.mapY })
        }
    }
}
</script>

<style lang="less" src="./course-resource-dialog.less"></style>
