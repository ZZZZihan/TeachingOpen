<template>
  <div>
    <div class="panel-works">
      <a-card class="search-card" :bordered="false">
        <j-dict-select-tag
          style="width: 200px;"
          :defaultShowAll="true"
          @change="handleChangeCategory"
          v-model="courseCategory"
          :trigger-change="true"
          dictCode="course_category"
          placeholder="请选择课程分类"
        />
        <a-divider type="vertical"></a-divider>
        <j-dict-select-tag
          style="width: 200px;"
          :defaultShowAll="true"
          @change="handleChangeType"
          v-model="courseType"
          :trigger-change="true"
          dictCode="course_type"
          placeholder="请选择课程性质"
        />
        <a-divider type="vertical"></a-divider>
        <a-input-search @search="onSearch" style="width: 200px;" placeholder="请输入课程名称"></a-input-search>
      </a-card>
      <h1 class="panel-title">
        <a-icon type="calculator" theme="twoTone" />
        推荐课程
      </h1>
      <a-row type="flex" justify="start" :gutter="[24, 24]">
        <a-col
          v-for="item in datasource"
          :key="item.id"
          :xs="24"
          :sm="12"
          :md="12"
          :lg="8"
          :xl="6">
          <a-card class="work-card">
            <a @click="toDetail(item)" target="_blank">
              <img class="work-cover" :src="item.courseCover_url" :alt="item.courseName" />
            </a>
            <div class="work-info">
              <p>{{ item.courseName }}</p>
            </div>
          </a-card>
        </a-col>
      </a-row>
      <a-spin style="margin:50px auto;" v-if="loading"/>
      <a-alert v-if="!loading && loadError" :message="loadError" type="error" show-icon />
      <a-empty v-if="!loading && !loadError && datasource.length==0" description="暂无符合条件的课程"/>
      <a-button v-if="!loading && hasMore && (loadError || datasource.length>0)" class="load-more" type="dashed" @click="getData">{{ loadError ? '重新加载' : '加载更多……' }}</a-button>
    </div>

    <j-modal
      :visible="showCourseDetail"
      :title="currentCourse.courseName"
      :width="500"
      @cancel="showCourseDetail=false"
      @ok="toCourse"
      okText="去上课"
      cancelText="关闭"
    >
      <div v-html="currentCourse.courseDesc"></div>
    </j-modal>
  </div>
</template>

<script>
import { getAction } from '@/api/manage'
export default {
    name: 'CourseList',
    data () {
        return {
            loading: false,
            datasource: [],
            page: 0,
            hasMore: true,
            loadError: '',
            requestId: 0,
            courseType: '',
            courseCategory: '',
            courseName: '',
            showCourseDetail: false,
            currentCourse: {}
        }
    },
    created () {
        this.getData()
    },
    beforeDestroy () {
        this.requestId += 1
    },
    methods: {
        onSearch (v) {
            this.courseName = v
            return this.resetData()
        },
        handleChangeCategory (v) {
            this.courseCategory = v
            return this.resetData()
        },
        handleChangeType (v) {
            this.courseType = v
            return this.resetData()
        },
        resetData () {
            // Invalidate the previous query before starting a new first-page request.
            this.requestId += 1
            this.loading = false
            this.page = 0
            this.hasMore = true
            this.datasource = []
            this.loadError = ''
            return this.getData()
        },
        getData () {
            if (this.loading || !this.hasMore) {
                return
            }
            const requestId = ++this.requestId
            const nextPage = this.page + 1
            this.loading = true
            this.loadError = ''
            return getAction('/teaching/teachingCourse/getHomeCourse', {
                courseType: this.courseType,
                courseCategory: this.courseCategory,
                courseName: this.courseName,
                orderBy: 'time',
                pageSize: this._isMobile() ? 12 : 24,
                pageNo: nextPage
            }).then((res) => {
                if (requestId !== this.requestId) {
                    return
                }
                if (!res || !res.success || !res.result || !Array.isArray(res.result.records) ||
                    typeof res.result.total !== 'number' || !Number.isFinite(res.result.total) || res.result.total < 0) {
                    throw new Error('Invalid course response')
                }
                const records = res.result.records
                this.datasource = this.datasource.concat(records)
                // Only advance after success so retrying a failed request cannot skip a page.
                this.page = nextPage
                this.hasMore = records.length > 0 && this.datasource.length < res.result.total
            }).catch(() => {
                if (requestId === this.requestId) {
                    this.loadError = '课程加载失败，请重试。'
                }
            }).finally(() => {
                if (requestId === this.requestId) {
                    this.loading = false
                }
            })
        },
        toDetail (item) {
            this.showCourseDetail = true
            this.currentCourse = item
        },
        toCourse () {
            this.$router.push('/teaching/mineCourse/courseUnitCard?id=' + this.currentCourse.id)
        },
        _isMobile () {
            return (
                navigator.userAgent.match(
                    /(phone|pad|pod|iPhone|iPod|ios|Android|Mobile|BlackBerry|IEMobile|MQQBrowser|JUC|Fennec|wOSBrowser|BrowserNG|WebOS|Symbian|Windows Phone)/i
                ) != null
            )
        }
    }
}
</script>

<style lang="less" scoped>

  .panel-works {
    margin: 30px 0;
  }
  .panel-title {
    margin-top: 24px;
    font-size: 26px;
    color: #333;
  }
  .work-card {
    border-radius: 10px;
    overflow: hidden;
    box-shadow: rgb(218, 218, 218) 2px 2px 5px;
    max-height: 300px;
    min-width: 200px;
    /deep/.ant-card-body {
      padding: 0px;
    }
    .work-cover {
      width: 100%;
      max-height: 150px;
    }
    .work-info{
      padding: 10px;
    }
    .work-author {
      span {
        line-height: 40px;
      }
    }
    .ant-tag {
      float: right;
    }
    > div {
      padding: 10px;
      margin: 10px;
    }
  }
  .load-more {
    display: block;
    margin: 10px auto;
    text-align: center;
  }
</style>
