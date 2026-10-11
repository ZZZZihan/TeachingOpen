<#assign validatorTableName = tableName!''>
        validatorRules: {
<#list columns as po>
  <#include "core.ftl">
</#list>
        },
