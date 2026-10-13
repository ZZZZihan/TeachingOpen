package org.jeecg.modules.system.service;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.jeecg.common.exception.JeecgBootException;
import java.util.*;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/** Small bounded validation rules used by the existing normal form checker. */
public final class CheckRuleValidator {
    private static final ObjectMapper JSON = new ObjectMapper();
    private CheckRuleValidator() { }
    public static JSONArray rules(String raw) {
        if (raw == null || raw.length() > 1024) throw invalid();
        try (JsonParser parser = JSON.getFactory().createParser(raw)) {
            JsonNode rows = JSON.readTree(parser);
            if (rows == null || !rows.isArray() || rows.size() < 1 || rows.size() > 20 || parser.nextToken() != null) throw invalid();
            JSONArray checked = new JSONArray();
            for (JsonNode row : rows) {
                if (!row.isObject() || row.size() != 3 || !row.has("digits") || !row.has("pattern") || !row.has("message")) throw invalid();
                JsonNode digitValue = row.get("digits");
                String digits = digitValue.isIntegralNumber() ? digitValue.asText() : string(row, "digits", 3);
                String pattern = string(row, "pattern", 256), message = string(row, "message", 256);
                if (!"*".equals(digits) && (!digits.matches("[0-9]{1,3}") || Integer.parseInt(digits) < 1 || Integer.parseInt(digits) > 256)) throw invalid();
                safePattern(pattern);
                JSONObject value = new JSONObject(); value.put("digits",digits); value.put("pattern",pattern); value.put("message",message);
                checked.add(value);
            }
            return checked;
        } catch (java.io.IOException failure) { throw invalid(); }
    }
    private static String string(JsonNode row, String key, int max) {
        JsonNode value = row.get(key);
        if (!value.isTextual() || value.asText().isEmpty() || value.asText().length() > max) throw invalid();
        return value.asText();
    }
    private static void safePattern(String pattern) {
        // Preserve repository form patterns, but exclude grouping, backreferences,
        // alternation and multiple variable-width repetitions before invoking Java regex.
        boolean inClass = false; int variable = 0;
        for (int i = 0; i < pattern.length(); i++) {
            char current = pattern.charAt(i);
            if (current == '\\') {
                if (++i >= pattern.length() || ".[]{}?+*()|^$\\-dDsSwWntfr".indexOf(pattern.charAt(i)) < 0) throw invalid();
                continue;
            }
            if (current == '[') inClass = true;
            else if (current == ']') inClass = false;
            else if (!inClass) {
                if (current == '(' || current == ')' || current == '|') throw invalid();
                if (current == '*' || current == '+' || current == '?') variable++;
                if (current == '{') {
                    int end = pattern.indexOf('}', i);
                    if (end < 0) throw invalid();
                    String repetition = pattern.substring(i + 1, end);
                    if (!repetition.matches("[0-9]{1,3}(,[0-9]{0,3})?")) throw invalid();
                    String[] limits = repetition.split(",", -1);
                    for (String limit : limits) if (!limit.isEmpty() && Integer.parseInt(limit) > 256) throw invalid();
                    if (limits.length > 1) variable++;
                    i = end;
                }
                if (variable > 1) throw invalid();
            }
        }
        try { Pattern.compile(pattern); } catch (PatternSyntaxException failure) { throw invalid(); }
    }
    private static JeecgBootException invalid() { return new JeecgBootException("校验规则格式不受支持"); }
}
