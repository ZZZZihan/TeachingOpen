<template>
  <section class="registration-entry" aria-labelledby="registration-entry-title">
    <div class="registration-copy">
      <h3 id="registration-entry-title">加入学习，一起成长</h3>
      <p>创建账号，开启课程学习与作品创作。</p>
      <router-link class="registration-button" :to="{ name: 'register' }">立即注册</router-link>
    </div>
    <div class="registration-qr">
      <div ref="qr" class="qr-image" role="img" aria-label="扫码打开本平台注册页">
        <qrcode-vue :value="registrationUrl" :size="160" level="H" />
      </div>
      <p>手机扫码注册</p>
      <button type="button" class="qr-download" @click="downloadQr">下载注册二维码</button>
      <p v-if="downloadError" class="download-error" role="alert">{{ downloadError }}</p>
    </div>
  </section>
</template>

<script>
import QrcodeVue from 'qrcode.vue'
import { registrationUrl, qrPngCanvas } from '@/utils/registrationEntry'

export default {
    name: 'RegistrationEntry',
    components: { QrcodeVue },
    data () { return { downloadError: '' } },
    computed: {
        registrationUrl () { return registrationUrl(this.$router, window.location.origin) }
    },
    methods: {
        downloadQr () {
            this.downloadError = ''
            try {
                const source = this.$refs.qr.querySelector('canvas')
                const image = qrPngCanvas(source, document)
                const link = document.createElement('a')
                link.href = image.toDataURL('image/png')
                link.download = '平台注册二维码.png'
                document.body.appendChild(link)
                link.click()
                document.body.removeChild(link)
            } catch (_) {
                this.downloadError = '二维码暂时无法下载，请稍后重试。'
            }
        }
    }
}
</script>

<style scoped lang="less">
.registration-entry { display: flex; flex-direction: column; align-items: stretch; gap: 24px; padding: 24px; background: #f7f4f7; border: 1px solid #e9e1e8; border-radius: 12px; }
.registration-copy { min-width: 0; }
h3 { margin: 0 0 10px; font-size: 20px; color: #20252b; }
p { margin: 0 0 18px; color: #59646e; line-height: 1.6; }
.registration-button { display: inline-block; padding: 10px 24px; background: #74256a; border-radius: 6px; color: #fff; font-weight: 600; }
.registration-button:hover { background: #602058; }
.registration-qr { text-align: center; min-width: 0; }
.qr-image { display: inline-block; max-width: 100%; box-sizing: border-box; padding: 32px; background: #fff; border-radius: 6px; line-height: 0; }
.qr-image /deep/ canvas { max-width: 100%; height: auto !important; }
.registration-qr p { margin: 8px 0; font-size: 13px; }
.qr-download { padding: 4px 8px; border: 0; background: transparent; color: #74256a; cursor: pointer; text-decoration: underline; }
.registration-qr .download-error { max-width: 224px; color: #a61d24; }
a:focus-visible, button:focus-visible { outline: 2px solid #74256a; outline-offset: 4px; }
@media (max-width: 680px) { .registration-entry { flex-direction: column; align-items: stretch; padding: 20px; } .registration-button { text-align: center; } .registration-qr { align-self: center; } }
</style>
