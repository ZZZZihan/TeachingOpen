<template>
  <j-modal
    :visible="visible"
    :width="1200"
    title="地图编辑器"
    :okClose="false"
    :confirmLoading="saving"
    :okButtonProps="{ props: { disabled: loading || saving || !!loadError || unitList.length === 0 } }"
    :maskClosable="false"
    :fullscreen="true"
    :switchFullscreen="true"
    @ok="handleOk"
    @cancel="handleCancel"
  >
    <a-alert v-if="loadError || saveError" type="error" :message="loadError || saveError" show-icon />
    <a-spin :spinning="loading" tip="正在加载课程单元…">
    <div class="map-config" :inert="saving ? '' : null">
      <a-row>
        <a-col :span="8">
          <a-select v-model="currentUnitId" style="width: 200px">
            <a-select-option v-for="unit in unitList" :key="unit.id">
              {{ unit.unitName }}
            </a-select-option>
          </a-select>
        </a-col>
        <a-col :span="8">
          <div class="position">
            <a-input prefix="X:" v-model="currentUnit.mapX" :disabled="saving || !currentUnitId" @change="saved = false" placeholder="x坐标" />
            <a-input prefix="Y:" v-model="currentUnit.mapY" :disabled="saving || !currentUnitId" @change="saved = false" placeholder="y坐标" />
          </div>
        </a-col>
        <a-col :span="8"> <a-tag color="red">双击图标开始拖动/结束拖动</a-tag> </a-col>
      </a-row>
    </div>
    <div
      class="map-wrapper"
      ref="mapWrapper"
      :style="{ background: 'url(' + mapUrl + ') no-repeat', backgroundSize: 'auto', height: '1000px' }"
    >
      <div
        v-for="unit in unitList"
        :key="unit.id"
        class="unit"
        :style="{ left: unit.mapX + 'px', top: unit.mapY + 'px' }"
        @click="selectUnit(unit.id)"
        @dblclick="drag(unit.id)"
      >
        <i :class="currentUnitId==unit.id?'flag active':'flag'" :style="mapIconUrl?'background-image:url('+mapIconUrl+')':''"></i>
        <!-- <div class="unit-title">{{ unit.unitName }}</div> -->
        <a-tag>{{ unit.unitName }}</a-tag>
      </div>
    </div>
    </a-spin>
  </j-modal>
</template>

<script>
import { getAction, putAction } from '@/api/manage'
export default {
  name: 'TeachingMapEditor',
  data() {
    return {
      visible: false, courseInfo: {}, mapUrl: '', mapIconUrl: '', unitList: [],
      currentUnitId: '', currentUnit: {}, flags: false, saved: true,
      requestVersion: 0, loading: false, saving: false, loadError: '', saveError: ''
    }
  },
  watch: {
    currentUnitId(value) {
      if (this.flags && this.currentUnit.id !== value) this.stopDrag()
      this.currentUnit = this.unitList.find(unit => unit.id === value) || {}
    }
  },
  beforeDestroy() {
    this.requestVersion += 1
    this.stopDrag()
  },
  methods: {
    isCurrent(version) { return this.visible && version === this.requestVersion },
    beginOpen(courseId) {
      this.requestVersion += 1
      this.stopDrag()
      this.courseInfo = { id: courseId }
      this.mapUrl = ''
      this.mapIconUrl = ''
      this.unitList = []
      this.currentUnitId = ''
      this.currentUnit = {}
      this.saved = true
      this.loading = true
      this.saving = false
      this.loadError = ''
      this.saveError = ''
      this.visible = true
      return this.requestVersion
    },
    open(courseInfo) {
      const version = this.beginOpen(courseInfo && courseInfo.id)
      if (!courseInfo || !courseInfo.id) {
        this.loading = false
        this.loadError = '请先保存课程，再编辑课程地图。'
        return
      }
      this.applyCourse(courseInfo)
      return this.loadUnits(courseInfo.id, null, version)
    },
    async openById(courseId, unitId) {
      const version = this.beginOpen(courseId)
      if (!courseId) {
        this.loading = false
        this.loadError = '请选择所属课程后再编辑地图。'
        return
      }
      try {
        const result = await getAction('/teaching/teachingCourse/queryById', { id: courseId })
        if (!this.isCurrent(version)) return
        if (!result || result.success !== true || !result.result || result.result.id !== courseId) throw new Error('Course unavailable')
        this.applyCourse(result.result)
        await this.loadUnits(courseId, unitId, version)
      } catch (error) {
        if (this.isCurrent(version)) {
          this.loading = false
          this.loadError = '课程地图加载未成功，请关闭后重新打开。'
        }
      }
    },
    applyCourse(course) {
      this.courseInfo = { ...course }
      this.mapUrl = course.courseMap_url || ''
      this.mapIconUrl = course.courseMapIcon_url || ''
    },
    async loadUnits(courseId, selectUnitId, version) {
      const units = []
      try {
        let total = 0
        let pageNo = 1
        do {
          const res = await getAction('/teaching/teachingCourseUnit/list', { courseId, pageNo, pageSize: 100 })
          if (!this.isCurrent(version)) return
          if (!res || res.success !== true || !res.result || !Array.isArray(res.result.records)) throw new Error('Unit list unavailable')
          const records = res.result.records
          total = Number(res.result.total)
          if (!Number.isSafeInteger(total) || total < 0 || records.length > 100 ||
              new Set(records.map(unit => unit.id)).size !== records.length ||
              records.some(unit => unit.courseId !== courseId || !unit.id || units.some(existing => existing.id === unit.id))) throw new Error('Invalid unit page')
          if (records.length === 0 && units.length < total) throw new Error('Incomplete unit page')
          units.push(...records)
          pageNo += 1
        } while (units.length < total)
        if (!this.isCurrent(version)) return
        this.unitList = units
        this.currentUnitId = units.some(unit => unit.id === selectUnitId) ? selectUnitId : (units[0] ? units[0].id : '')
        this.currentUnit = units.find(unit => unit.id === this.currentUnitId) || {}
      } catch (error) {
        if (this.isCurrent(version)) this.loadError = '课程单元加载未成功，请关闭后重新打开。'
      } finally {
        if (this.isCurrent(version)) this.loading = false
      }
    },
    async handleOk() {
      if (!this.visible || this.loading || this.saving || this.loadError || !this.unitList.length) return
      this.stopDrag()
      const units = this.unitList.map(({ id, mapX, mapY }) => ({ id, mapX: Number(mapX), mapY: Number(mapY) }))
      if (this.unitList.some(unit => unit.mapX === null || unit.mapY === null || unit.mapX === '' || unit.mapY === '') ||
          units.some(unit => !Number.isInteger(unit.mapX) || !Number.isInteger(unit.mapY) ||
            Math.abs(unit.mapX) > 2147483647 || Math.abs(unit.mapY) > 2147483647)) {
        this.saveError = '请为每个课程单元填写有效的整数坐标。'
        return
      }
      const version = this.requestVersion
      this.saving = true
      this.saveError = ''
      try {
        const res = await putAction('/teaching/teachingCourseUnit/editBatch', { courseId: this.courseInfo.id, units })
        if (!this.isCurrent(version)) return
        if (!res || res.success !== true) {
          this.saveError = '地图保存未成功，坐标修改已保留。请检查课程权限后重试。'
          return
        }
        this.saved = true
        this.$emit('saved', { courseId: this.courseInfo.id, units })
        this.$message.success('地图保存成功')
      } catch (error) {
        if (this.isCurrent(version)) this.saveError = '未能确认地图保存结果，坐标修改已保留。请先核对后再决定是否重试。'
      } finally {
        if (this.isCurrent(version)) this.saving = false
      }
    },
    close() {
      this.requestVersion += 1
      this.stopDrag()
      this.visible = false
      this.loading = false
      this.saving = false
      this.unitList = []
      this.currentUnitId = ''
      this.currentUnit = {}
    },
    handleCancel() {
      this.stopDrag()
      if (this.saving) return
      if (this.saved) return this.close()
      const version = this.requestVersion
      this.$confirm({
        title: '放弃未保存的地图修改？',
        content: '关闭后，本次坐标修改将丢失。',
        onOk: () => { if (this.isCurrent(version)) this.close() }
      })
    },
    selectUnit(unitId) {
      if (!this.saving) {
        if (this.currentUnitId !== unitId) this.stopDrag()
        this.currentUnitId = unitId
      }
    },
    stopDrag() {
      window.removeEventListener('mousemove', this.mouseMove)
      this.flags = false
    },
    drag(unitId) {
      if (!this.visible || this.loading || this.saving) return
      const wasDragging = this.flags && this.currentUnitId === unitId
      this.stopDrag()
      this.currentUnitId = unitId
      this.currentUnit = this.unitList.find(unit => unit.id === unitId) || {}
      if (!wasDragging && this.currentUnitId) {
        this.flags = true
        window.addEventListener('mousemove', this.mouseMove)
      }
    },
    mouseMove(event) {
      const wrapper = this.$refs.mapWrapper
      if (!this.visible || !this.flags || this.saving || !this.currentUnitId || !wrapper) return
      const bounds = wrapper.getBoundingClientRect()
      this.saved = false
      this.currentUnit.mapY = Math.round(event.clientY - bounds.top - 25)
      this.currentUnit.mapX = Math.round(event.clientX - bounds.left - 25)
    }
  }
}
</script>

<style lang="less" scoped>
.map-config {
  padding-bottom: 10px;
  .position {
    .ant-input-affix-wrapper {
      width: 80px;
      display: inline-block;
      margin-right: 10px;
    }
  }
}
.map-editor {
  width: 1000px;
  height: 700px;
}
.map-wrapper {
  .map {
    position: absolute;
  }
  .unit {
    width: 50px;
    height: 0;
    position: relative;
    display: block;
    .flag {
      display: block;
      width: 64px;
      height: 64px;
      background-image: url('/img/position.png');
      background-repeat: no;
      background-size: 64px 64px;
      opacity: .5;
      // margin: 10px 0;
      // border-radius: 0px 18px 31px 18px;
      // transform: rotate(225deg);
      // background: radial-gradient(#aedbe6, #57b0f3d4, #128fec);;
      // -webkit-box-shadow:rgba(66,140,240,0.5) 0px 10px 16px;
    }
    .active{
      opacity: 1;
    }
    .unit-title {
      background-color: #52c41ab3;
      display: block;
      width: fit-content;
      padding: 0.4em 0.6em 0.3em;
      font-size: 75%;
      font-weight: 700;
      line-height: 1;
      color: #fff;
      text-align: center;
      white-space: nowrap;
      vertical-align: baseline;
      border-radius: 0.25em;
    }
  }
}
</style>