<#assign validatorTableName = (sub.tableName)!''>
        validatorRules: {
<#list sub.colums as po>
  <#include "core.ftl">
</#list>
        },
