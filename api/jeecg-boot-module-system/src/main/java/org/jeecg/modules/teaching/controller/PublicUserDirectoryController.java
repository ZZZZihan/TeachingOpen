package org.jeecg.modules.teaching.controller;

import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.teaching.service.PublicUserDirectoryService;
import org.jeecg.modules.teaching.vo.PublicUserDirectory;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/teaching/user")
public class PublicUserDirectoryController {
    private final PublicUserDirectoryService service;
    public PublicUserDirectoryController(PublicUserDirectoryService service) { this.service = service; }

    @GetMapping("/publicDirectory")
    public Result<PublicUserDirectory> publicDirectory(@RequestParam(defaultValue = "1") long pageNo) {
        Result<PublicUserDirectory> result = new Result<>();
        result.setSuccess(true);
        result.setResult(service.load(pageNo));
        return result;
    }
}
