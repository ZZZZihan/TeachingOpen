<template>
  <form class="recovery-form" novalidate :aria-busy="submitting" @submit.prevent="nextStep">
    <h2>确认你的账号</h2><p class="step-intro">请输入教学平台账号或已绑定的手机号。</p>
    <div class="field">
      <label for="recovery-account">账号或手机号</label>
      <input
        id="recovery-account"
        ref="account"
        v-model="account"
        name="username"
        autocomplete="username"
        placeholder="请输入账号或手机号"
        :disabled="submitting"
        :aria-invalid="!!errors.account"
        :aria-describedby="errors.account ? 'recovery-account-error' : null"
        @input="accountChanged">
      <p v-if="errors.account" id="recovery-account-error" class="field-error">{{ errors.account }}</p>
    </div>
    <div class="field">
      <div class="field-label"><label for="recovery-captcha">图形验证码</label><button class="text-button" type="button" :disabled="captchaLoading || submitting" @click="refreshCaptcha">换一张</button></div>
      <div class="captcha-row">
        <input
          id="recovery-captcha"
          ref="captcha"
          v-model="captcha"
          name="captcha"
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
          placeholder="输入图中字符"
          :disabled="submitting"
          :aria-invalid="!!errors.captcha"
          aria-describedby="recovery-captcha-help">
        <button class="captcha-image" type="button" :disabled="captchaLoading || submitting" :aria-label="captchaImage ? '刷新图形验证码' : '重新加载图形验证码'" @click="refreshCaptcha"><img v-if="captchaImage" :src="captchaImage" alt="找回密码图形验证码" @error="captchaFailed"><span v-else>{{ captchaLoading ? '加载中…' : '点击重试' }}</span></button>
      </div>
      <p id="recovery-captcha-help" :class="errors.captcha || captchaError ? 'field-error' : 'field-hint'" aria-live="polite">{{ errors.captcha || captchaError || '看不清？点击图片或换一张。' }}</p>
    </div>
    <p v-if="submitError" ref="submitError" class="form-error" role="alert" tabindex="-1">{{ submitError }}</p>
    <button class="primary-button" type="submit" :disabled="submitting || captchaLoading || !captchaImage">{{ submitting ? '正在确认…' : '下一步：手机验证' }}</button>
    <router-link class="back-login" :to="{ name: 'login' }">← 返回登录</router-link>
  </form>
</template>

<script>
import { getRecoveryCaptcha, checkRecoveryCaptcha, queryRecoveryAccount } from '@/api/accountRecovery'
import { isMainlandPhone, recoveryError } from '@/utils/accountRecovery'

export default {
    name: 'Step1',
    props: { initialAccount: { type: String, default: '' } },
    data () { return { account: this.initialAccount, captcha: '', errors: {}, submitError: '', submitting: false, captchaImage: '', captchaError: '', captchaLoading: false, checkKey: '', imageVersion: 0, lookupVersion: 0, disposed: false } },
    created () { this.refreshCaptcha() },
    beforeDestroy () { this.disposed = true; this.imageVersion++; this.lookupVersion++; this.captcha = '' },
    methods: {
        accountChanged () { this.lookupVersion++; this.submitting = false; this.submitError = ''; this.errors = {} },
        captchaFailed () { this.captchaImage = ''; this.captchaError = '验证码未能加载，请点击重试。' },
        focus (name) { this.$nextTick(() => { if (!this.disposed && this.$refs[name]) this.$refs[name].focus() }) },
        async refreshCaptcha () {
            const version = ++this.imageVersion
            this.lookupVersion++
            this.submitting = false
            this.checkKey = `${Date.now()}-${version}`
            this.captcha = ''; this.errors = { ...this.errors, captcha: '' }; this.captchaImage = ''; this.captchaError = ''; this.captchaLoading = true
            try {
                const res = await getRecoveryCaptcha(this.checkKey)
                if (this.disposed || version !== this.imageVersion) return
                if (!res.success || typeof res.result !== 'string' || !res.result.startsWith('data:image/')) throw new Error('captcha')
                this.captchaImage = res.result
            } catch (_) { if (!this.disposed && version === this.imageVersion) this.captchaFailed() } finally {
                if (!this.disposed && version === this.imageVersion) this.captchaLoading = false
            }
        },
        async nextStep () {
            if (this.submitting || this.captchaLoading || !this.captchaImage) return
            this.errors = {}; this.submitError = ''
            const account = this.account.trim()
            if (!account) this.errors.account = '请输入账号或手机号。'
            if (!this.captcha.trim()) this.errors.captcha = '请输入图形验证码。'
            const first = Object.keys(this.errors)[0]
            if (first) { this.focus(first); return }
            const version = ++this.lookupVersion
            this.submitting = true
            let fallback = '图形验证码未通过，请重新输入。'
            try {
                const checked = await checkRecoveryCaptcha({ captcha: this.captcha.trim(), checkKey: this.checkKey })
                if (this.disposed || version !== this.lookupVersion || account !== this.account.trim()) return
                if (!checked.success) throw new Error('captcha')
                fallback = '未找到可找回的账号，请检查账号或联系平台管理员。'
                const isPhone = isMainlandPhone(account)
                const res = await queryRecoveryAccount(isPhone ? { phone: account } : { username: account })
                if (this.disposed || version !== this.lookupVersion || account !== this.account.trim()) return
                if (!res.success || !res.result || !res.result.username) throw new Error('account')
                this.captcha = ''
                this.$emit('nextStep', { username: res.result.username, maskedPhone: res.result.phone || '', enteredPhone: isPhone ? account : '' })
            } catch (error) {
                if (this.disposed || version !== this.lookupVersion) return
                this.submitError = recoveryError(error, fallback)
                await this.refreshCaptcha()
                this.focus('submitError')
            } finally { if (!this.disposed && version === this.lookupVersion) this.submitting = false }
        }
    }
}
</script>
