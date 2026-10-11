package org.jeecg.modules.system.service.impl;

import org.jeecg.common.util.FillRuleUtil;
import org.jeecg.modules.system.entity.SysFillRule;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysFillRuleMapper;
import org.jeecg.modules.system.service.GlobalResourceService;
import org.jeecg.modules.system.service.ISysFillRuleService;
import org.springframework.stereotype.Service;
import java.util.Date;
import java.util.UUID;

@Service("sysFillRuleServiceImpl")
public class SysFillRuleServiceImpl extends GlobalResourceService<SysFillRuleMapper, SysFillRule> implements ISysFillRuleService {
    @Override protected String entityId(SysFillRule value) { return value.getId(); }
    @Override protected SysFillRule writable(SysFillRule input, boolean editing, SysUser actor) {
        if (input == null) throw invalid();
        String ruleClass = FillRuleUtil.requireSupported(code(input.getRuleCode()), input.getRuleClass());
        SysFillRule value = new SysFillRule().setRuleName(text(input.getRuleName(), 100, true)).setRuleCode(input.getRuleCode())
                .setRuleClass(ruleClass).setRuleParams(FillRuleUtil.parameters(ruleClass, input.getRuleParams()).toJSONString());
        if (editing) value.setId(checkedId(input.getId())).setUpdateBy(actor.getUsername()).setUpdateTime(new Date());
        else value.setId(UUID.randomUUID().toString().replace("-", "")).setCreateBy(actor.getUsername()).setCreateTime(new Date());
        return value;
    }
}
