package org.jeecg.modules.system.controller;

import javax.servlet.http.HttpServletRequest;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.system.model.DuplicateCheckVo;
import org.jeecg.modules.system.service.DuplicateCheckService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;

@RestController
@RequestMapping("/sys/duplicate")
@Api(tags = "重复校验")
public class DuplicateCheckController {
    private static final Set<String> PARAMETERS = new HashSet<>(Arrays.asList("purpose", "fieldVal", "dataId", "_t"));
    private final DuplicateCheckService checks;

    public DuplicateCheckController(DuplicateCheckService checks) { this.checks = checks; }

    @GetMapping("/check")
    @ApiOperation("按表单用途校验重复值")
    public Result<Object> doDuplicateCheck(DuplicateCheckVo input, HttpServletRequest request) {
        try {
            // Reject legacy identifiers even when a valid purpose accompanies them.
            for (Map.Entry<String, String[]> parameter : request.getParameterMap().entrySet()) {
                if (!PARAMETERS.contains(parameter.getKey()) || parameter.getValue().length != 1) {
                    throw new IllegalArgumentException("不支持此校验参数");
                }
            }
            return checks.available(input) ? Result.ok("该值可用！") : Result.error("该值不可用，系统中已存在！");
        } catch (UnauthorizedException denied) {
            return Result.error(403, denied.getMessage());
        } catch (IllegalArgumentException invalid) {
            return Result.error(400, invalid.getMessage());
        }
    }
}
