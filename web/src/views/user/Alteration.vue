<template>
  <section class="recovery-page" aria-labelledby="recovery-title">
    <header class="recovery-heading"><span class="eyebrow">天津工业大学 · 账号服务</span><h1 id="recovery-title">找回密码</h1><p>通过账号绑定的手机号验证身份，重新设置登录密码。</p></header>
    <ol class="recovery-steps" aria-label="找回密码步骤">
      <li v-for="(title, index) in steps" :key="title" :class="{ active: currentTab === index, complete: currentTab > index }" :aria-current="currentTab === index ? 'step' : null"><span aria-hidden="true">{{ currentTab > index ? '✓' : index + 1 }}</span>{{ title }}</li>
    </ol>
    <Step1 v-if="currentTab === 0" :initialAccount="initialAccount" @nextStep="accountFound" />
    <Step2 v-if="currentTab === 1" :userList="userList" @nextStep="phoneVerified" @prevStep="changeAccount" />
    <Step3 v-if="currentTab === 2" :userList="userList" @nextStep="passwordChanged" @prevStep="verifyAgain" @verificationInvalid="clearVerification" />
    <Step4 v-if="currentTab === 3" :userList="userList" />
  </section>
</template>

<script>
import Step1 from './Step1'
import Step2 from './Step2'
import Step3 from './Step3'
import Step4 from './Step4'

export default {
    name: 'Alteration',
    components: { Step1, Step2, Step3, Step4 },
    data () { return { steps: ['确认账号', '手机验证', '设置密码', '完成'], currentTab: 0, initialAccount: '', userList: {} } },
    beforeDestroy () { this.userList = {}; this.initialAccount = '' },
    methods: {
        accountFound (data) { if (this.currentTab === 0) { this.userList = data; this.currentTab = 1 } },
        phoneVerified (data) { if (this.currentTab === 1) { this.userList = data; this.currentTab = 2 } },
        passwordChanged (data) { if (this.currentTab === 2) { this.userList = { username: data.username }; this.initialAccount = ''; this.currentTab = 3 } },
        changeAccount () { this.initialAccount = this.userList.username || ''; this.userList = {}; this.currentTab = 0 },
        clearVerification () { this.userList = { ...this.userList, smscode: '', resendAt: 0 } },
        verifyAgain () { this.userList = { ...this.userList, enteredPhone: this.userList.phone, phone: '', smscode: '' }; this.currentTab = 1 }
    }
}
</script>

<style lang="less">
.recovery-page {
  width: 100%; color: #20252b;
  .eyebrow { color: #74256a; font-size: 11px; letter-spacing: .1em; font-weight: 600; }
  .recovery-heading h1 { font-size: 29px; font-weight: 600; margin: 10px 0 8px; color: #20252b; }
  .recovery-heading p { color: #626b73; font-size: 14px; line-height: 1.8; margin: 0; }
  .recovery-steps { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 28px 0 30px; border-bottom: 1px solid #e1e4e8; }
  .recovery-steps li { color: #737b82; font-size: 12px; padding: 0 0 16px; display: flex; align-items: center; gap: 6px; white-space: nowrap; }
  .recovery-steps li > span { width: 20px; height: 20px; border: 1px solid #cbd1d6; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0; font-size: 11px; }
  .recovery-steps .active { color: #74256a; font-weight: 600; box-shadow: 0 2px #74256a; }
  .recovery-steps .active > span { color: #fff; background: #74256a; border-color: #74256a; }
  .recovery-steps .complete > span { color: #74256a; border-color: #74256a; }
  .recovery-form h2, .recovery-success h2 { color: #20252b; font-size: 20px; margin: 0 0 9px; font-weight: 600; }
  .step-intro, .field-hint { color: #707980; font-size: 12px; line-height: 1.8; margin: 0 0 22px; }
  .field { margin-bottom: 21px; }
  .field label { display: block; font-size: 14px; font-weight: 500; margin-bottom: 9px; }
  .field-label { display: flex; justify-content: space-between; align-items: baseline; }
  input { width: 100%; min-width: 0; height: 46px; border: 1px solid #cbd1d6; border-radius: 3px; padding: 0 13px; background: #fff; color: #20252b; font: inherit; font-size: 15px; box-sizing: border-box; }
  input::placeholder { color: #858d94; }
  input[aria-invalid="true"] { border-color: #b63c46; }
  input:disabled { background: #f7f8f8; }
  input:focus, button:focus-visible, a:focus-visible { outline: 2px solid #74256a; outline-offset: 3px; }
  .captcha-row, .sms-row { display: grid; grid-template-columns: minmax(0, 1fr) 126px; gap: 12px; }
  .captcha-image { padding: 0; border: 1px solid #cbd1d6; border-radius: 3px; background: #f6f7f8; cursor: pointer; color: #59646e; overflow: hidden; }
  .captcha-image img { width: 100%; height: 44px; object-fit: contain; display: block; }
  .text-button { color: #59646e; font-size: 12px; border: 0; padding: 0; background: none; cursor: pointer; }
  .field-hint, .field-error { margin: 8px 0 0; font-size: 12px; line-height: 1.7; }
  .field-error { color: #a2303c; }
  .form-error { padding: 12px 14px; border-left: 2px solid #a2303c; color: #92303a; background: #fbf2f2; font-size: 13px; line-height: 1.8; margin: 0 0 18px; }
  .form-note { background: #f6f3f6; border-left: 2px solid #74256a; padding: 12px 14px; font-size: 13px; line-height: 1.8; margin: 0 0 22px; overflow-wrap: anywhere; }
  .form-note strong { color: #20252b; font-weight: 500; }
  .primary-button, .secondary-button { min-height: 46px; border-radius: 3px; font: inherit; font-size: 14px; cursor: pointer; padding: 10px 16px; }
  .primary-button { border: 1px solid #74256a; background: #74256a; color: #fff; display: block; text-align: center; width: 100%; }
  .primary-button:hover:not(:disabled) { background: #592052; color: #fff; }
  .secondary-button { border: 1px solid #cbd1d6; background: #fff; color: #59646e; }
  .sms-row .secondary-button { padding: 0 6px; font-size: 12px; }
  button:disabled { cursor: not-allowed; opacity: .65; }
  .form-actions { display: flex; gap: 12px; margin-top: 26px; }
  .form-actions .primary-button { flex: 1; }
  .form-actions .secondary-button { flex-shrink: 0; }
  .back-login { display: inline-block; margin-top: 24px; color: #59646e; font-size: 13px; }
  .recovery-success { padding: 8px 0 4px; }
  .success-mark { width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; color: #74256a; background: #f6f3f6; font-size: 24px; border-radius: 50%; margin-bottom: 18px; }
  .recovery-success p { color: #626b73; font-size: 14px; line-height: 1.9; margin-bottom: 28px; }
  @media (max-width: 380px) { .recovery-steps { gap: 4px; } .recovery-steps li { font-size: 11px; gap: 4px; } .captcha-row, .sms-row { grid-template-columns: minmax(0, 1fr) 108px; gap: 8px; } }
}
</style>
