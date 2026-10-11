package org.jeecg.common.util;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.jeecg.common.constant.FillRuleConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.handler.IFillRuleHandler;
import java.util.*;

/** Only the two locally implemented code generators are configurable/executable. */
public class FillRuleUtil {
    public static final String ORGANIZATION = "org.jeecg.modules.system.rule.OrgCodeRule";
    public static final String CATEGORY = "org.jeecg.modules.system.rule.CategoryCodeRule";
    private static final Set<String> SUPPORTED = new HashSet<>(Arrays.asList(ORGANIZATION, CATEGORY));
    private static final ObjectMapper JSON_TREE = new ObjectMapper();

    public static String requireSupported(String code, String ruleClass) {
        if (code == null || !code.matches("[A-Za-z0-9_-]{1,100}") || !SUPPORTED.contains(ruleClass)
                || (FillRuleConstant.DEPART.equals(code) && !ORGANIZATION.equals(ruleClass))
                || (FillRuleConstant.CATEGORY.equals(code) && !CATEGORY.equals(ruleClass))) throw invalid();
        return ruleClass;
    }

    public static JSONObject parameters(String ruleClass, String raw) {
        if (!SUPPORTED.contains(ruleClass)) throw invalid();
        if (raw == null || raw.trim().isEmpty()) raw = "{}";
        if (raw.length() > 1024) throw invalid();
        try {
            JsonNode node = JSON_TREE.reader().with(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS).readTree(raw);
            if (node == null || !node.isObject() || node.size() > 1) throw invalid();
            String allowed = ORGANIZATION.equals(ruleClass) ? "parentId" : "pid";
            JSONObject values = new JSONObject();
            Iterator<String> names = node.fieldNames();
            while (names.hasNext()) {
                String name = names.next(); JsonNode value = node.get(name);
                if (!allowed.equals(name) || !value.isTextual() || !value.asText().matches("[A-Za-z0-9_-]{0,64}")) throw invalid();
                values.put(name, value.asText());
            }
            return values;
        } catch (java.io.IOException failure) { throw invalid(); }
    }

    @SuppressWarnings("unchecked")
    public static Object executeRule(String ruleCode, JSONObject formData) {
        if (ruleCode == null || !ruleCode.matches("[A-Za-z0-9_-]{1,100}")) throw invalid();
        ServiceImpl impl = (ServiceImpl) SpringContextUtils.getBean("sysFillRuleServiceImpl");
        QueryWrapper<Object> query = new QueryWrapper<>(); query.eq("rule_code", ruleCode);
        JSONObject entity = JSON.parseObject(JSON.toJSONString(impl.getOne(query)));
        if (entity == null) throw invalid();
        String ruleClass = requireSupported(ruleCode, entity.getString("ruleClass"));
        JSONObject params = parameters(ruleClass, entity.getString("ruleParams"));
        JSONObject form = parameters(ruleClass, formData == null ? "{}" : formData.toJSONString());
        try {
            // The class name has matched a fixed local allowlist before class loading.
            IFillRuleHandler handler = (IFillRuleHandler) Class.forName(ruleClass).newInstance();
            return handler.execute(params, form);
        } catch (ReflectiveOperationException failure) { throw invalid(); }
    }
    private static JeecgBootException invalid() { return new JeecgBootException("填值规则配置不可用"); }
}
