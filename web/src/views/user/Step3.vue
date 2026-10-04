<template>
  <form class="recovery-form" novalidate :aria-busy="submitting" @submit.prevent="nextStep">
    <h2>设置新的登录密码</h2><p class="step-intro">为账号 {{ userList.username }} 设置新密码。</p>
    <div class="field">
      <label for="recovery-password">新密码</label><input
        id="recovery-password"
        ref="password"
        v-model="password"
        name="password"
        type="password"
        autocomplete="new-password"
        maxlength="64"
        placeholder="请输入新密码"
        :disabled="submitting || verificationRequired"
        :aria-invalid="!!errors.password"
        aria-describedby="recovery-password-help">
      <p id="recovery-password-help" :class="errors.password ? 'field-error' : 'field-hint'">{{ errors.password || '8–64 位，含英文字母、数字和特殊符号，不含空格或中文；无需同时包含大小写。' }}</p>
    </div>
    <div class="field">
      <label for="recovery-confirm-password">再次输入新密码</label><input
        id="recovery-confirm-password"
        ref="confirmPassword"
        v-model="confirmPassword"
        name="confirmPassword"
        type="password"
        autocomplete="new-password"
        maxlength="64"
        placeholder="请再次输入新密码"
        :disabled="submitting || verificationRequired"
        :aria-invalid="!!errors.confirmPassword"
        :aria-describedby="errors.confirmPassword ? 'recovery-confirm-error' : null">
      <p v-if="errors.confirmPassword" id="recovery-confirm-error" class="field-error">{{ errors.confirmPassword }}</p>
    </div>
    <p v-if="submitError" ref="submitError" class="form-error" role="alert" tabindex="-1">{{ submitError }}</p>
    <div class="form-actions"><button class="secondary-button" type="button" @click="prevStep">返回手机验证</button><button v-if="!verificationRequired" class="primary-button" type="submit" :disabled="submitting">{{ submitting ? '正在更新…' : '确认修改密码' }}</button></div>
    <router-link class="back-login" :to="{ name: 'login', params: { username: userList.username } }">← 返回登录</router-link>
  </form>
</template>

<script>
import { changeRecoveryPassword } from '@/api/accountRecovery'
import { passwordProblem } from '@/utils/accountRecovery'

export default {
    name: 'Step3',
    props: { userList: { type: Object, required: true } },
    data () { return { password: '', confirmPassword: '', errors: {}, submitError: '', submitting: false, verificationRequired: false, requestVersion: 0, disposed: false } },
    beforeDestroy () { this.disposed = true; this.requestVersion++; this.clearPasswords() },
    methods: {
        focus (name) { this.$nextTick(() => { if (!this.disposed && this.$refs[name]) this.$refs[name].focus() }) },
        clearPasswords () { this.password = ''; this.confirmPassword = '' },
        async nextStep () {
            if (this.submitting || this.verificationRequired) return
            this.errors = {}; this.submitError = ''
            const problem = passwordProblem(this.password)
            if (problem) this.errors.password = problem
            if (!this.confirmPassword) this.errors.confirmPassword = '请再次输入新密码。'
            else if (this.confirmPassword !== this.password) this.errors.confirmPassword = '两次输入的密码不一致。'
            const first = Object.keys(this.errors)[0]
            if (first) { this.focus(first); return }
            if (!this.userList.smscode || !this.userList.phone || !this.userList.username) { this.requireVerification('手机验证已失效，请返回手机验证并重新获取验证码。'); return }
            const version = ++this.requestVersion; const username = this.userList.username
            this.submitting = true
            try {
                const res = await changeRecoveryPassword({ username, phone: this.userList.phone, smscode: this.userList.smscode, password: this.password })
                if (this.disposed || version !== this.requestVersion || username !== this.userList.username) return
                if (!res.success) {
                    const message = res.recoveryState === 'reset_committed'
                        ? '密码已更新，但登录状态清理未完成。请尝试使用新密码登录；若仍需重置，返回手机验证重新获取验证码。'
                        : res.recoveryState === 'reset_unknown' || res.code >= 500
                            ? '提交结果未能确认。请先尝试使用新密码登录；若仍需重置，返回手机验证并重新获取验证码。'
                            : '密码未能更新。验证码可能已失效或已使用，请返回手机验证并重新获取验证码。'
                    this.requireVerification(message)
                    return
                }
                this.clearPasswords()
                this.$emit('nextStep', { username })
            } catch (_) {
                if (this.disposed || version !== this.requestVersion) return
                this.requireVerification('提交结果未能确认。请先尝试登录；若仍需重置，返回手机验证并重新获取验证码。')
            } finally { if (!this.disposed && version === this.requestVersion) this.submitting = false }
        },
        requireVerification (message) { this.clearPasswords(); this.verificationRequired = true; this.submitError = message; this.$emit('verificationInvalid'); this.focus('submitError') },
        prevStep () { this.requestVersion++; this.submitting = false; this.clearPasswords(); this.$emit('prevStep') }
    }
}
</script>
