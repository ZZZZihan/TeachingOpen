package org.jeecg.modules.system.service;

import com.alibaba.fastjson.JSONObject;
import com.aliyuncs.exceptions.ClientException;
import org.jeecg.common.util.DySmsEnum;
import org.jeecg.common.util.DySmsHelper;
import org.springframework.stereotype.Component;

/** Recovery-only adapter; tests replace this bean and never contact the SMS provider. */
@Component
public class PasswordResetSmsSender {
    public boolean send(String phone, String code) throws ClientException {
        JSONObject params = new JSONObject();
        params.put("code", code);
        return DySmsHelper.sendSms(phone, params, DySmsEnum.FORGET_PASSWORD_TEMPLATE_CODE, false);
    }
}
