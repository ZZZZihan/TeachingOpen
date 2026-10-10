<template>
  <main class="registration-page">
    <div class="registration-heading"><span>天津工业大学 · 学习与创作</span><h1>创建你的账号</h1><p>使用手机号和密码登录教学平台。</p></div>
    <form novalidate :aria-busy="submitting" @submit.prevent="submit">
      <div v-for="field in fields" :key="field.key" class="field">
        <label :for="'register-' + field.key">{{ field.label }}</label>
        <input :id="'register-' + field.key" v-model="form[field.key]" :name="field.key" :type="field.type || 'text'" :autocomplete="field.autocomplete" :maxlength="field.maximum" :inputmode="field.key === 'phone' ? 'tel' : null" :disabled="submitting" :aria-invalid="!!errors[field.key]" :aria-describedby="errors[field.key] ? field.key + '-error' : null">
        <p v-if="errors[field.key]" :id="field.key + '-error'" class="field-error">{{ errors[field.key] }}</p>
      </div>
      <fieldset :disabled="submitting"><legend>身份</legend><label><input v-model="form.identity" type="radio" name="identity" value="student"> 学生</label><label><input v-model="form.identity" type="radio" name="identity" value="teacher"> 教师</label><p v-if="errors.identity" class="field-error">{{ errors.identity }}</p></fieldset>
      <p class="privacy-note">姓名将脱敏展示，学校和身份将展示在首页。教师身份用于个人资料，教学管理权限由管理员开通。</p>
      <p v-if="submitError" role="alert" class="field-error">{{ submitError }}</p>
      <button type="submit" :disabled="submitting">{{ submitting ? '正在注册…' : '注册账号' }}</button>
      <router-link class="login-link" to="/user/login">使用已有账号登录</router-link>
    </form>
  </main>
</template>

<script>
import { postAction } from '@/api/manage'
import { isMainlandPhone, passwordProblem, recoveryError } from '@/utils/accountRecovery'

export default {
    name: 'Register',
    data () {
        return {
            submitting: false, submitError: '', errors: {},
            form: { phone: '', password: '', confirmation: '', realname: '', school: '', identity: '' },
            fields: [
                { key: 'phone', label: '手机号', autocomplete: 'username', maximum: 11 },
                { key: 'password', label: '密码（8–64位，包含字母、数字和特殊符号）', type: 'password', autocomplete: 'new-password', maximum: 64 },
                { key: 'confirmation', label: '确认密码', type: 'password', autocomplete: 'new-password', maximum: 64 },
                { key: 'realname', label: '姓名', autocomplete: 'name', maximum: 100 },
                { key: 'school', label: '学校（请填写全称）', autocomplete: 'organization', maximum: 256 }
            ]
        }
    },
    methods: {
        async submit () {
            if (this.submitting) return
            const form = this.form
            const errors = {}
            if (!isMainlandPhone(form.phone.trim())) errors.phone = '请输入正确的11位手机号。'
            const passwordError = passwordProblem(form.password)
            if (passwordError) errors.password = passwordError.replace('新密码', '密码')
            if (!form.confirmation || form.password !== form.confirmation) errors.confirmation = '两次输入的密码需一致。'
            if (!form.realname.trim()) errors.realname = '请填写姓名。'
            if (!form.school.trim()) errors.school = '请填写学校。'
            if (!['student', 'teacher'].includes(form.identity)) errors.identity = '请选择身份。'
            this.errors = errors
            this.submitError = ''
            if (Object.keys(errors).length) return
            this.submitting = true
            try {
                const response = await postAction('/sys/user/register', {
                    phone: form.phone.trim(), password: form.password,
                    realname: form.realname.trim(), school: form.school.trim(), identity: form.identity
                })
                if (!response.success) {
                    this.submitError = response.message || '注册失败，请稍后重试。'
                    return
                }
                form.password = ''
                form.confirmation = ''
                await this.$router.push({ name: 'registerResult', params: { phone: form.phone.trim() } })
            } catch (error) {
                this.submitError = recoveryError(error, '注册请求失败，请稍后重试。')
            } finally {
                this.submitting = false
            }
        }
    }
}
</script>

<style scoped>
.registration-page { max-width: 480px; margin: 36px auto; padding: 24px; color: #27333b; }
.registration-heading span { color: #74256a; font-size: 12px; }
h1 { margin: 12px 0; font-size: 30px; }
.registration-heading p, .privacy-note { color: #69747c; line-height: 1.7; }
.field { margin-top: 18px; }
.field label { display: block; margin-bottom: 8px; }
.field input { width: 100%; padding: 12px; border: 1px solid #bec6cc; border-radius: 4px; }
.field input:focus { outline: 2px solid #74256a; outline-offset: 2px; }
fieldset { margin: 20px 0; border: 0; padding: 0; }
fieldset label { display: inline-block; margin-right: 24px; }
legend { margin-bottom: 10px; font-size: 14px; }
.field-error { color: #a12834; margin-top: 8px; }
.privacy-note { font-size: 12px; }
button { width: 100%; padding: 12px; background: #74256a; color: white; border: 0; border-radius: 4px; cursor: pointer; }
button:disabled { opacity: .65; cursor: wait; }
.login-link { display: block; text-align: center; margin-top: 18px; color: #74256a; }
</style>
