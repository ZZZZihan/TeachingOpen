package org.jeecg.modules.quartz.service;

import java.util.*;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.message.job.SendMsgJob;
import org.jeecg.modules.quartz.job.SampleJob;
import org.jeecg.modules.quartz.job.SampleParamJob;
import org.quartz.Job;

/** Only these reviewed, compiled task types can be selected by the administration API. */
public final class ManagedJobTypes {
    private static final Map<String, Class<? extends Job>> TYPES;
    static {
        Map<String, Class<? extends Job>> values = new LinkedHashMap<>();
        values.put("sample", SampleJob.class);
        values.put("sample-parameter", SampleParamJob.class);
        values.put("send-message", SendMsgJob.class);
        TYPES = Collections.unmodifiableMap(values);
    }
    private ManagedJobTypes() { }
    public static Class<? extends Job> jobClass(String type) {
        Class<? extends Job> value = TYPES.get(type);
        if (value == null) throw new JeecgBootException("不支持的任务类型");
        return value;
    }
    public static String typeForClass(String name) {
        for (Map.Entry<String, Class<? extends Job>> entry : TYPES.entrySet()) {
            if (entry.getValue().getName().equals(name)) return entry.getKey();
        }
        throw new JeecgBootException("不支持的任务类型");
    }
    public static List<String> names() { return new ArrayList<>(TYPES.keySet()); }
}
