<template>
  <form class="recovery-form" novalidate :aria-busy="verifying" @submit.prevent="nextStep">
    <h2>验证绑定的手机号</h2><p class="step-intro">填写完整手机号，接收并输入短信验证码。</p>
    <div class="form-note">账号：<strong>{{ userList.username }}</strong><br><span v-if="userList.maskedPhone">已绑定手机号提示：{{ userList.maskedPhone }}</span><span v-else>请使用此账号已绑定的手机号。</span></div>
    <div class="field">
      <label for="recovery-phone">完整的绑定手机号</label>
      <input
        id="recovery-phone"
        ref="phone"
        v-model="phone"
        name="phone"
        type="tel"
        inputmode="numeric"
        autocomplete="tel"
        maxlength="11"
        placeholder="请输入 11 位手机号"
        :disabled="verifying || sending"
        :aria-invalid="!!errors.phone"
        aria-describedby="recovery-phone-help"
        @input="phoneChanged">
      <p id="recovery-phone-help" :class="errors.phone ? 'field-error' : 'field-hint'">{{ errors.phone || '手机号须与账号绑定记录一致；无法接收短信时请联系平台管理员。' }}</p>
    </div>
    <div class="field">
      <label for="recovery-smscode">短信验证码</label>
      <div class="sms-row"><input
        id="recovery-smscode"
        ref="smscode"
        v-model="smscode"
        name="smscode"
        inputmode="numeric"
        autocomplete="one-time-code"
        maxlength="6"
        placeholder="输入短信验证码"
        :disabled="verifying"
        :aria-invalid="!!errors.smscode"
        aria-describedby="recovery-sms-help"><button class="secondary-button" type="button" :disabled="sending || verifying || remaining > 0" @click="getCaptcha">{{ sending ? '正在发送…' : remaining > 0 ? resendLabel : '获取验证码' }}</button></div>
      <p id="recovery-sms-help" :class="errors.smscode ? 'field-error' : 'field-hint'" aria-live="polite">{{ errors.smscode || smsNotice || '验证码有效期以短信和服务端为准，请及时完成验证。' }}</p>
    </div>
    <p v-if="submitError" ref="submitError" class="form-error" role="alert" tabindex="-1">{{ submitError }}</p>
    <div class="form-actions"><button class="secondary-button" type="button" @click="prevStep">修改账号</button><button class="primary-button" type="submit" :disabled="sending || verifying">{{ verifying ? '正在验证…' : '下一步：设置密码' }}</button></div>
    <router-link class="back-login" :to="{ name: 'login' }">← 返回登录</router-link>
  </form>
</template>

<script>
import { sendRecoverySms, verifyRecoveryPhone } from '@/api/accountRecovery'
import { isMainlandPhone, recoveryError } from '@/utils/accountRecovery'

export default {
    name: 'Step2',
    props: { userList: { type: Object, required: true } },
    data () { return { phone: this.userList.enteredPhone || '', smscode: '', errors: {}, submitError: '', smsNotice: '', sending: false, verifying: false, remaining: 0, resendAt: this.userList.resendAt || 0, timer: null, requestVersion: 0, disposed: false } },
    computed: { resendLabel () { return Math.floor(this.remaining / 60) + ':' + String(this.remaining % 60).padStart(2, '0') + ' 后重发' } },
    created () { this.updateCountdown(); if (this.remaining > 0) this.timer = setInterval(this.updateCountdown, 1000) },
    beforeDestroy () { this.invalidate(); this.disposed = true; this.smscode = ''; this.clearTimer() },
    methods: {
        focus (name) { this.$nextTick(() => { if (!this.disposed && this.$refs[name]) this.$refs[name].focus() }) },
        invalidate () { this.requestVersion++; this.sending = false; this.verifying = false },
        phoneChanged () { this.invalidate(); this.smscode = ''; this.submitError = ''; this.smsNotice = ''; this.errors = {} },
        clearTimer () { if (this.timer !== null) clearInterval(this.timer); this.timer = null },
        updateCountdown () { this.remaining = Math.max(0, Math.ceil((this.resendAt - Date.now()) / 1000)); if (!this.remaining) this.clearTimer() },
        startCountdown () { this.clearTimer(); this.resendAt = Date.now() + 600000; this.updateCountdown(); this.timer = setInterval(this.updateCountdown, 1000) },
        validPhone () {
            this.errors = {}
            if (!isMainlandPhone(this.phone.trim())) { this.errors.phone = '请输入 11 位中国大陆手机号。'; this.focus('phone'); return false }
            return true
        },
        async getCaptcha () {
            if (this.sending || this.verifying || this.remaining > 0 || !this.validPhone()) return
            const phone = this.phone.trim(); const username = this.userList.username; const version = ++this.requestVersion
            this.submitError = ''; this.smsNotice = ''; this.sending = true
            try {
                const res = await sendRecoverySms({ mobile: phone, smsmode: '2', username })
                if (this.disposed || version !== this.requestVersion || phone !== this.phone.trim() || username !== this.userList.username) return
                if (!res.success && res.recoveryState === 'code_active') { this.submitError = '验证码仍有效或正在发送，请使用已收到的验证码，或稍后重新获取。'; this.focus('submitError'); return }
                if (!res.success) throw new Error('sms')
                this.smscode = ''
                this.smsNotice = '短信已发送，请查看手机。请在服务端有效期内使用；10 分钟后可尝试重新获取。'
                this.startCountdown()
                this.focus('smscode')
            } catch (error) {
                if (this.disposed || version !== this.requestVersion) return
                this.submitError = recoveryError(error, '短信未能发送，请检查手机号是否与账号绑定后重试。')
                this.focus('submitError')
            } finally { if (!this.disposed && version === this.requestVersion) this.sending = false }
        },
        async nextStep () {
            if (this.sending || this.verifying || !this.validPhone()) return
            this.submitError = ''
            if (!/^\d{6}$/.test(this.smscode.trim())) { this.errors.smscode = '请输入 6 位短信验证码。'; this.focus('smscode'); return }
            const phone = this.phone.trim(); const smscode = this.smscode.trim(); const username = this.userList.username; const version = ++this.requestVersion
            this.verifying = true
            try {
                const res = await verifyRecoveryPhone({ username, phone, smscode })
                if (this.disposed || version !== this.requestVersion || phone !== this.phone.trim() || username !== this.userList.username) return
                if (!res.success) throw new Error('verification')
                this.smscode = ''
                this.$emit('nextStep', { username, phone, smscode, maskedPhone: this.userList.maskedPhone, resendAt: this.resendAt })
            } catch (error) {
                if (this.disposed || version !== this.requestVersion) return
                this.submitError = recoveryError(error, '验证未通过，请核对绑定手机号与验证码，或重新获取验证码。')
                this.focus('submitError')
            } finally { if (!this.disposed && version === this.requestVersion) this.verifying = false }
        },
        prevStep () { this.invalidate(); this.smscode = ''; this.clearTimer(); this.$emit('prevStep') }
    }
}
</script>
