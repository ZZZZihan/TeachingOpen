<template>
  <div class="login-page">
    <section class="login-intro" aria-labelledby="intro-title">
      <span class="eyebrow">TeachingOpen · 学习与创作</span>
      <h1 id="intro-title">动手实践，<br>学以致用。</h1>
      <p>浏览课程，完成练习与创作。<br class="desktop-break">登录后继续你的学习任务。</p>
      <router-link to="/courseList" class="explore-link">先看看课程 <span aria-hidden="true">↗</span></router-link>
      <div class="intro-bottom"><span class="intro-rule"></span>学习 · 实践 · 创造 · 分享</div>
    </section>
    <section class="login-form-panel" aria-labelledby="login-title">
      <div class="form-heading"><span class="eyebrow">你的学习空间</span><h2 id="login-title">欢迎回来</h2><p>使用手机号或已有教学平台账号登录。</p></div>
      <p v-if="$route.query.reason === 'expired'" class="session-note" role="status">登录已过期，请重新登录后继续。</p>
      <form novalidate :aria-busy="submitting" @submit.prevent="submit">
        <div class="field">
          <label for="login-username">手机号或账号</label>
          <input
            id="login-username"
            ref="username"
            v-model="username"
            name="username"
            autocomplete="username"
            placeholder="请输入手机号或已有账号"
            :disabled="submitting"
            :aria-invalid="!!errors.username"
            :aria-describedby="errors.username ? 'username-error' : null">
          <p v-if="errors.username" id="username-error" class="field-error">{{ errors.username }}</p>
        </div>
        <div class="field">
          <div class="field-label"><label for="login-password">密码</label><router-link to="/user/alteration">忘记密码？</router-link></div>
          <div class="password-input"><input
            id="login-password"
            ref="password"
            v-model="password"
            name="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            placeholder="请输入密码"
            :disabled="submitting"
            :aria-invalid="!!errors.password"
            :aria-describedby="errors.password ? 'password-error' : null"><button type="button" :disabled="submitting" :aria-pressed="showPassword" :aria-label="showPassword ? '隐藏密码' : '显示密码'" @click="showPassword = !showPassword">{{ showPassword ? '隐藏' : '显示' }}</button></div>
          <p v-if="errors.password" id="password-error" class="field-error">{{ errors.password }}</p>
        </div>
        <div class="field">
          <div class="field-label"><label for="login-captcha">验证码</label><button class="text-button" type="button" :disabled="captchaLoading || submitting" @click="refreshCaptcha">换一张</button></div>
          <div class="captcha-row"><input
            id="login-captcha"
            ref="captcha"
            v-model="captcha"
            name="captcha"
            autocomplete="off"
            autocapitalize="off"
            spellcheck="false"
            placeholder="输入图中字符"
            :disabled="submitting"
            :aria-invalid="!!errors.captcha"
            aria-describedby="captcha-help"><button class="captcha-image" type="button" :disabled="captchaLoading || submitting" :aria-label="captchaImage ? '刷新验证码图片' : '重新加载验证码'" @click="refreshCaptcha"><img v-if="captchaImage" :src="captchaImage" alt="登录验证码" @error="captchaFailed"><span v-else>{{ captchaLoading ? '加载中…' : '点击重试' }}</span></button></div>
          <p id="captcha-help" :class="errors.captcha || captchaError ? 'field-error' : 'field-hint'" aria-live="polite">{{ errors.captcha || captchaError || '看不清？点击图片或换一张。' }}</p>
        </div>
        <p v-if="submitError" ref="submitError" class="form-error" role="alert" tabindex="-1">{{ submitError }}</p>
        <button class="submit-button" type="submit" :disabled="submitting || captchaLoading || !captchaImage">{{ submitting ? '正在登录…' : '登录并继续' }}<span v-if="!submitting" aria-hidden="true">→</span></button>
      </form>
      <p v-if="allowRegistration" class="register-note">还没有账号？<router-link to="/user/register">注册账号</router-link></p>
      <p v-else class="register-note">没有账号？请联系你的教师或平台管理员。</p>
      <router-link to="/index" class="back-home">← 返回首页</router-link>
    </section>
  </div>
</template>

<script>
import { getLoginCaptcha } from '@/api/login'
import { safeRedirect, loginErrorMessage } from '@/utils/session'

export default {
    name: 'Login',
    data () {
        return { username: this.$route.params.username || '',
            password: '',
            captcha: '',
            showPassword: false,
            errors: {},
            submitError: '',
            submitting: false,
            captchaImage: '',
            captchaError: '',
            captchaLoading: false,
            checkKey: '',
            requestVersion: 0,
            disposed: false }
    },
    computed: {
        allowRegistration () { return (this.$store.getters.sysConfig || {}).allowReg === '1' }
    },
    created () { this.refreshCaptcha() },
    beforeDestroy () { this.disposed = true; this.requestVersion++ },
    methods: {
        captchaFailed () {
            this.captchaImage = ''
            this.captchaError = '验证码未能加载，请点击重试。'
        },
        async refreshCaptcha () {
            const version = ++this.requestVersion
            this.checkKey = `${Date.now()}-${version}`
            this.captcha = ''
            this.errors = { ...this.errors, captcha: '' }
            this.captchaImage = ''
            this.captchaError = ''
            this.captchaLoading = true
            try {
                const response = await getLoginCaptcha(this.checkKey)
                if (this.disposed || version !== this.requestVersion) return
                if (!response.success || typeof response.result !== 'string' || !response.result.startsWith('data:image/')) throw new Error('验证码加载失败')
                this.captchaImage = response.result
            } catch (_) {
                if (!this.disposed && version === this.requestVersion) this.captchaFailed()
            } finally {
                if (!this.disposed && version === this.requestVersion) this.captchaLoading = false
            }
        },
        async submit () {
            if (this.submitting || this.captchaLoading || !this.captchaImage) return
            this.errors = {}
            this.submitError = ''
            if (!this.username.trim()) this.errors.username = '请输入账号。'
            if (!this.password) this.errors.password = '请输入密码。'
            if (!this.captcha.trim()) this.errors.captcha = '请输入验证码。'
            const first = Object.keys(this.errors)[0]
            if (first) { this.$nextTick(() => this.$refs[first].focus()); return }
            this.submitting = true
            try {
                await this.$store.dispatch('Login', { username: this.username.trim(),
                    password: this.password,
                    captcha: this.captcha.trim(),
                    checkKey: this.checkKey })
                if (this.disposed) return
                this.password = ''
                await this.$router.replace(safeRedirect(this.$route.query.redirect))
            } catch (error) {
                if (this.disposed) return
                this.submitError = loginErrorMessage(error)
                await this.refreshCaptcha()
                if (!this.disposed) this.$nextTick(() => this.$refs.submitError && this.$refs.submitError.focus())
            } finally {
                if (!this.disposed) this.submitting = false
            }
        }
    }
}
</script>

<style scoped>
.login-page { display: grid; grid-template-columns: 1fr 1fr; min-height: 680px; max-width: 1120px; margin: 0 auto; }
.login-intro { background: #123e67; color: #fff; padding: 70px 56px 38px; display: flex; flex-direction: column; }
.eyebrow { font-size: 11px; letter-spacing: .14em; font-weight: 600; }
.login-intro .eyebrow { color: #dce9f5; }
.login-intro h1 { color: #fff; font-size: 44px; line-height: 1.4; letter-spacing: -.03em; font-weight: 500; margin: 66px 0 24px; }
.login-intro p { color: #d5e5f5; font-size: 16px; line-height: 1.9; margin-bottom: 30px; }
.explore-link { color: #fff; font-size: 14px; align-self: flex-start; padding-bottom: 7px; border-bottom: 1px solid #82949d; }
.explore-link span { margin-left: 20px; }
.intro-bottom { color: #ccdef0; font-size: 12px; margin-top: auto; padding-top: 80px; }
.intro-rule { display: inline-block; width: 28px; border-top: 2px solid #9bc5ed; margin: 0 10px 4px 0; }
.login-form-panel { padding: 54px 64px 40px; background: #fff; }
.form-heading .eyebrow { color: #146fc2; }
.form-heading h2 { font-size: 30px; font-weight: 600; letter-spacing: -.03em; margin: 10px 0 8px; color: #20252b; }
.form-heading p { color: #626b73; margin-bottom: 30px; font-size: 14px; }
.field { margin-bottom: 21px; }
.field label { display: block; color: #20252b; font-size: 14px; font-weight: 500; margin-bottom: 9px; }
.field-label { display: flex; justify-content: space-between; align-items: baseline; }
.field-label a, .text-button { color: #59646e; font-size: 12px; }
.text-button { border: 0; padding: 0; background: none; cursor: pointer; }
input { display: block; box-sizing: border-box; width: 100%; min-width: 0; height: 46px; border: 1px solid #cbd1d6; border-radius: 3px; padding: 0 13px; background: #fff; color: #20252b; font: inherit; font-size: 15px; transition: border-color .15s; }
input::placeholder { color: #858d94; }
input[aria-invalid="true"] { border-color: #b63c46; }
input:focus, button:focus-visible, a:focus-visible { outline: 2px solid #146fc2; outline-offset: 3px; }
input:disabled { background: #f7f8f8; }
.password-input { position: relative; }
.password-input input { padding-right: 60px; }
.password-input button { position: absolute; right: 1px; top: 1px; height: 44px; border: 0; padding: 0 12px; background: transparent; color: #59646e; font-size: 12px; cursor: pointer; }
.captcha-row { display: grid; grid-template-columns: minmax(0, 1fr) 126px; gap: 12px; }
.captcha-image { padding: 0; border: 1px solid #cbd1d6; border-radius: 3px; background: #f6f7f8; cursor: pointer; color: #59646e; overflow: hidden; }
.captcha-image img { width: 100%; height: 44px; object-fit: contain; }
.field-hint, .field-error { margin: 8px 0 0; font-size: 12px; line-height: 1.6; }
.field-hint { color: #707980; }
.field-error { color: #a2303c; }
.form-error, .session-note { padding: 12px 14px; border-left: 2px solid #146fc2; color: #92303a; background: #fbf2f2; font-size: 13px; line-height: 1.7; margin: 0 0 18px; }
.submit-button { width: 100%; min-height: 46px; display: flex; align-items: center; justify-content: center; gap: 20px; background: #146fc2; border: 1px solid #146fc2; border-radius: 3px; color: #fff; font-size: 15px; cursor: pointer; }
.submit-button:hover:not(:disabled) { background: #095b9e; }
button:disabled { cursor: not-allowed; opacity: .65; }
.register-note { color: #737b82; font-size: 12px; line-height: 1.8; margin: 19px 0 25px; }
.register-note a { color: #146fc2; margin-left: 8px; }
.back-home { font-size: 13px; color: #59646e; }
@media (max-width: 1000px) { .login-intro { padding: 54px 30px 32px; } .login-intro h1 { font-size: 36px; } .login-form-panel { padding: 48px 32px 36px; } }
@media (max-width: 680px) { .login-page { display: block; min-height: 0; } .login-intro { padding: 29px 24px; } .login-intro .eyebrow, .intro-bottom, .login-intro p, .explore-link { display: none; } .login-intro h1 { font-size: 26px; line-height: 1.5; margin: 0; } .login-intro h1 br { display: none; } .login-form-panel { padding: 32px 24px; } .form-heading h2 { font-size: 27px; } .form-heading p { margin-bottom: 26px; } }
</style>
