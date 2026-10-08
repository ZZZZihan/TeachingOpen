<template>
  <section class="registration" aria-labelledby="register-title">
    <span class="eyebrow">天工 · 你的学习空间</span>
    <h1 id="register-title">创建教学平台账号</h1>
    <p class="intro">注册后，登录平台开始学习与创作。</p>
    <div v-if="!allowRegistration" class="notice" role="status">
      <p>平台暂未开放注册，请联系你的教师或平台管理员。</p>
      <router-link to="/user/login">返回登录</router-link>
    </div>
    <form v-else novalidate :aria-busy="busy" @submit.prevent="submit">
      <div class="field">
        <label for="register-username">账号</label>
        <input
          id="register-username"
          ref="username"
          v-model="username"
          name="username"
          autocomplete="username"
          maxlength="32"
          placeholder="4–32 位英文字母、数字或下划线"
          :disabled="busy"
          :aria-invalid="!!errors.username"
          aria-describedby="register-username-help">
        <p id="register-username-help" :class="errors.username ? 'error' : 'hint'">{{ errors.username || '账号用于登录，注册后请妥善保存。' }}</p>
      </div>
      <div class="field">
        <label for="register-realname">姓名</label>
        <input
          id="register-realname"
          ref="realname"
          v-model="realname"
          name="realname"
          autocomplete="name"
          maxlength="100"
          placeholder="请输入姓名"
          :disabled="busy"
          :aria-invalid="!!errors.realname"
          :aria-describedby="errors.realname ? 'register-name-error' : null">
        <p v-if="errors.realname" id="register-name-error" class="error">{{ errors.realname }}</p>
      </div>
      <div class="field">
        <div class="label-row"><label for="register-password">密码</label><button class="text-button" type="button" :disabled="busy" :aria-pressed="showPassword" @click="showPassword = !showPassword">{{ showPassword ? '隐藏密码' : '显示密码' }}</button></div>
        <input
          id="register-password"
          ref="password"
          v-model="password"
          name="password"
          :type="showPassword ? 'text' : 'password'"
          autocomplete="new-password"
          maxlength="64"
          placeholder="请输入密码"
          :disabled="busy"
          :aria-invalid="!!errors.password"
          aria-describedby="register-password-help">
        <p id="register-password-help" :class="errors.password ? 'error' : 'hint'">{{ errors.password || '8–64 位，包含英文字母、数字和特殊符号，不含空格或中文。' }}</p>
      </div>
      <div class="field">
        <label for="register-confirm">确认密码</label>
        <input
          id="register-confirm"
          ref="confirmPassword"
          v-model="confirmPassword"
          name="confirmPassword"
          :type="showPassword ? 'text' : 'password'"
          autocomplete="new-password"
          maxlength="64"
          placeholder="再次输入密码"
          :disabled="busy"
          :aria-invalid="!!errors.confirmPassword"
          :aria-describedby="errors.confirmPassword ? 'register-confirm-error' : null">
        <p v-if="errors.confirmPassword" id="register-confirm-error" class="error">{{ errors.confirmPassword }}</p>
      </div>
      <p v-if="submitError" ref="submitError" class="notice error" role="alert" tabindex="-1">{{ submitError }}</p>
      <button class="submit-button" type="submit" :disabled="busy">{{ submitting ? '正在注册…' : '注册账号' }}<span v-if="!submitting" aria-hidden="true">→</span></button>
    </form>
    <p class="login-link">已有账号？<router-link to="/user/login">前往登录</router-link></p>
  </section>
</template>

<script>
import { registerAccount } from '@/api/registration'
import { passwordProblem, recoveryError } from '@/utils/accountRecovery'
import { registrationProblems, registrationError } from '@/utils/registration'

export default {
    name: 'Register',
    data () {
        return {
            username: '',
            realname: '',
            password: '',
            confirmPassword: '',
            showPassword: false,
            errors: {},
            submitError: '',
            submitting: false,
            disposed: false
        }
    },
    computed: {
        allowRegistration () { return (this.$store.getters.sysConfig || {}).allowReg === '1' },
        busy () { return this.submitting }
    },
    beforeDestroy () {
        this.disposed = true
        this.password = this.confirmPassword = ''
    },
    methods: {
        focusError () {
            const first = Object.keys(this.errors)[0] || 'submitError'
            this.$nextTick(() => this.$refs[first] && this.$refs[first].focus())
        },
        async submit () {
            if (this.busy || !this.allowRegistration) return
            this.submitError = ''
            this.errors = registrationProblems({ username: this.username.trim(), realname: this.realname })
            const passwordError = passwordProblem(this.password)
            if (passwordError) this.errors.password = passwordError.replace('新密码', '密码')
            if (!this.confirmPassword || this.confirmPassword !== this.password) this.errors.confirmPassword = '两次输入的密码不一致。'
            if (Object.keys(this.errors).length) { this.focusError(); return }
            this.submitting = true
            try {
                const response = await registerAccount({ username: this.username.trim(), realname: this.realname.trim(), password: this.password })
                if (this.disposed) return
                if (!response.success) {
                    this.submitError = registrationError(response, '注册未完成，请稍后重试，或尝试登录确认账号状态。')
                    this.focusError()
                    return
                }
                const username = this.username.trim()
                this.password = this.confirmPassword = ''
                await this.$router.replace({ name: 'registerResult', params: { username } })
            } catch (error) {
                if (!this.disposed) {
                    this.submitError = recoveryError(error, '注册结果暂时无法确认，请尝试登录或稍后重试。')
                    this.focusError()
                }
            } finally { if (!this.disposed) this.submitting = false }
        }
    }
}
</script>

<style scoped>
.registration { min-width: 0; }
.eyebrow { color: #74256a; font-size: 11px; letter-spacing: .12em; font-weight: 600; }
h1 { color: #20252b; font-size: 27px; font-weight: 600; line-height: 1.4; margin: 10px 0; }
.intro { color: #626b73; font-size: 14px; margin-bottom: 26px; }
.field { margin-bottom: 19px; }
label { display: block; color: #20252b; font-weight: 500; margin-bottom: 8px; }
.label-row { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
input { box-sizing: border-box; width: 100%; min-width: 0; height: 46px; padding: 0 12px; border: 1px solid #cbd1d6; border-radius: 3px; font: inherit; font-size: 15px; background: #fff; color: #20252b; }
input:disabled { background: #f7f8f8; }
input[aria-invalid="true"] { border-color: #b63c46; }
input:focus, button:focus-visible, a:focus-visible { outline: 2px solid #74256a; outline-offset: 3px; }
.hint, .error { font-size: 12px; line-height: 1.7; margin: 7px 0 0; overflow-wrap: anywhere; }
.hint { color: #626b73; }
.error { color: #a2303c; }
.text-button { border: 0; padding: 0; background: none; color: #59646e; font-size: 12px; cursor: pointer; }
.notice { padding: 12px 14px; border-left: 2px solid #74256a; background: #fbf2fa; margin-bottom: 18px; line-height: 1.7; }
.notice p { margin-bottom: 10px; }
.notice a, .login-link a { color: #74256a; }
.submit-button { width: 100%; min-height: 46px; display: flex; justify-content: center; align-items: center; gap: 20px; border: 1px solid #74256a; border-radius: 3px; background: #74256a; color: #fff; font-size: 15px; cursor: pointer; }
.submit-button:hover:not(:disabled) { background: #592052; }
button:disabled { cursor: not-allowed; opacity: .65; }
.login-link { color: #626b73; font-size: 13px; margin: 22px 0 0; }
.login-link a { margin-left: 8px; }
@media (max-width: 380px) { h1 { font-size: 24px; } }
</style>
