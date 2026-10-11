import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.util.FillRuleUtil;
import org.jeecg.modules.system.service.CheckRuleValidator;
import java.io.ByteArrayInputStream;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.*;

/** Local exported configuration only: never starts Spring or executes a fill handler/regex match. */
public final class RuleConfigurationPreflight {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final int MAX_ROWS = 5000;

    public static void main(String[] args) throws Exception {
        JsonNode input = JSON.reader()
                .with(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS)
                .with(com.fasterxml.jackson.core.JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
                .readTree(new ByteArrayInputStream(Files.readAllBytes(Paths.get(args[0]))));
        if (input == null || !input.isObject() || input.size() != 2
                || !input.has("fill_rules") || !input.has("check_rules")) throw new IllegalArgumentException("Expected two configuration arrays");
        ObjectNode report = JSON.createObjectNode();
        ArrayNode rows = report.putArray("rows"), issues = report.putArray("issues");
        Set<String> fillCodes = new HashSet<>();
        int failed = 0;
        for (String kind : Arrays.asList("fill_rules", "check_rules")) {
            JsonNode values = input.get(kind);
            if (!values.isArray() || values.size() > MAX_ROWS) throw new IllegalArgumentException("Invalid configuration array size");
            Set<String> codes = new HashSet<>();
            int index = 0;
            for (JsonNode value : values) {
                ObjectNode row = rows.addObject(); row.put("kind", kind); row.put("row_index", index++);
                ArrayNode errors = row.putArray("issues");
                String code = text(value, "rule_code");
                putSafeIdentifier(row, "id", text(value, "id"), 64);
                putSafeIdentifier(row, "rule_code", code, 100);
                if (!value.isObject()) errors.add("invalid_row_shape");
                if (code == null || !code.matches("[A-Za-z0-9_-]{1,100}")) errors.add("invalid_rule_code");
                else if (!codes.add(code)) errors.add("duplicate_rule_code");
                if ("fill_rules".equals(kind)) {
                    if (code != null) fillCodes.add(code);
                    String ruleClass = text(value, "rule_class");
                    boolean supported = true;
                    try { FillRuleUtil.requireSupported(code, ruleClass); }
                    catch (JeecgBootException invalid) { errors.add("unsupported_handler_or_builtin_binding"); supported = false; }
                    JsonNode params = value.get("rule_params");
                    if (params != null && !params.isNull() && !params.isTextual()) errors.add("invalid_parameters_type");
                    else if (supported) {
                        try { FillRuleUtil.parameters(ruleClass, text(value, "rule_params")); }
                        catch (JeecgBootException invalid) { errors.add("unsupported_parameters"); }
                    }
                } else {
                    try { CheckRuleValidator.rules(text(value, "rule_json")); }
                    catch (JeecgBootException invalid) { errors.add("unsupported_check_rule"); }
                }
                row.put("compatible", errors.size() == 0);
                if (errors.size() != 0) failed++;
            }
        }
        for (String required : Arrays.asList("org_num_role", "category_code_rule")) {
            if (!fillCodes.contains(required)) issues.addObject().put("code", "missing_builtin_rule").put("rule_code", required);
        }
        report.put("checked_rows", rows.size()); report.put("incompatible_rows", failed);
        report.put("compatible", failed == 0 && issues.size() == 0);
        Files.write(Paths.get(args[1]), JSON.writerWithDefaultPrettyPrinter().writeValueAsBytes(report), StandardOpenOption.CREATE_NEW);
    }
    private static String text(JsonNode value, String key) {
        JsonNode field = value.get(key);
        return field != null && field.isTextual() ? field.asText() : null;
    }
    private static void putSafeIdentifier(ObjectNode row, String key, String value, int max) {
        if (value != null && value.matches("[A-Za-z0-9_-]{1," + max + "}")) row.put(key, value);
    }
}
