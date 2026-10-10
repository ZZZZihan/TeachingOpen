<#include "../utils.ftl">
<#if po.isShow == 'Y' && poHasCheck(po)>
  <#if po.fieldName != 'id'>
          ${po.fieldName}: {
            rules: [
    <#assign fieldValidType = po.fieldValidType!''>
    <#-- 非空校验 -->
    <#if po.nullable == 'N' || fieldValidType == '*'>
              { required: true, message: '请输入${po.filedComment}!'},
    </#if>
    <#-- 唯一校验 -->
    <#if fieldValidType == 'only'>
      <#-- A generated form may only select a configured server-owned purpose. -->
      <#assign duplicatePurposes = {
        'sys_user.username': 'user_username', 'sys_user.phone': 'user_phone',
        'sys_user.email': 'user_email', 'sys_user.work_no': 'user_work_no',
        'sys_role.role_code': 'role_code', 'sys_dict.dict_code': 'dict_code',
        'sys_permission.perms': 'permission_perms', 'sys_position.code': 'position_code',
        'sys_depart_role.role_code': 'depart_role_code', 'sys_sms_template.template_code': 'message_template_code',
        'sys_fill_rule.rule_code': 'fill_rule_code', 'sys_check_rule.rule_code': 'check_rule_code',
        'sys_data_source.code': 'data_source_code'
      }>
      <#assign duplicatePurpose = duplicatePurposes[tableName + '.' + po.fieldDbName]!''>
      <#if duplicatePurpose == ''>
        <#stop '未配置此字段的唯一校验用途。请先在服务端配置固定查询、操作权限和编辑对象授权，再更新生成模板。'>
      </#if>
              { validator: (rule, value, callback) => validateDuplicateValue('${duplicatePurpose}', value, this.model.id, callback)},
    <#-- 6到16位数字 -->
    <#elseif fieldValidType == 'n6-16'>
              { pattern: /\d{6,18}/, message: '请输入6到16位数字!'},
    <#-- 6到16位任意字符 -->
    <#elseif fieldValidType == '*6-16'>
              { pattern: /^.{6,16}$/, message: '请输入6到16位任意字符!'},
    <#-- 6到18位字符串 -->
    <#elseif fieldValidType == 's6-18'>
              { pattern: /^.{6,18}$/, message: '请输入6到18位任意字符!'},
    <#-- 网址 -->
    <#elseif fieldValidType == 'url'>
              { pattern: /^(?:([A-Za-z]+):)?(\/{0,3})([0-9.\-A-Za-z]+)(?::(\d+))?(?:\/([^?#]*))?(?:\?([^#]*))?(?:#(.*))?$/, message: '请输入正确的网址!'},
    <#-- 电子邮件 -->
    <#elseif fieldValidType == 'e'>
              { pattern: /^([\w]+\.*)([\w]+)@[\w]+\.\w{3}(\.\w{2}|)$/, message: '请输入正确的电子邮件!'},
    <#-- 手机号码 -->
    <#elseif fieldValidType == 'm'>
              { pattern: /^1[3456789]\d{9}$/, message: '请输入正确的手机号码!'},
    <#-- 邮政编码 -->
    <#elseif fieldValidType == 'p'>
              { pattern: /^[1-9]\d{5}$/, message: '请输入正确的邮政编码!'},
    <#-- 字母 -->
    <#elseif fieldValidType == 's'>
              { pattern: /^[A-Z|a-z]+$/, message: '请输入字母!'},
    <#-- 数字 -->
    <#elseif fieldValidType == 'n'>
              { pattern: /^-?\d+\.?\d*$/, message: '请输入数字!'},
    <#-- 整数 -->
    <#elseif fieldValidType == 'z'>
              { pattern: /^-?\d+$/, message: '请输入整数!'},
    <#-- 金额 -->
    <#elseif fieldValidType == 'money'>
              { pattern: /^(([1-9][0-9]*)|([0]\.\d{0,2}|[1-9][0-9]*\.\d{0,2}))$/, message: '请输入正确的金额!'},
    <#-- 无校验 -->
    <#else>
      <#t>
    </#if>
            ]
          },
  </#if>
</#if>
