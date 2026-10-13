package org.jeecg.modules.system.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;
import org.jeecg.modules.system.entity.SysAnnouncement;

import java.util.Date;

/** The editable announcement fields. Publication, identity and audit fields are server-owned. */
@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class AnnouncementCommand {
    private String id;
    private String titile;
    private String msgContent;
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
    private Date startTime;
    @JsonFormat(timezone = "GMT+8", pattern = "yyyy-MM-dd HH:mm:ss")
    private Date endTime;
    private String priority;
    private String msgCategory;
    private String msgType;
    private String userIds;
    private String msgAbstract;

    public static AnnouncementCommand from(SysAnnouncement input) {
        AnnouncementCommand command = new AnnouncementCommand();
        command.setId(input.getId()); command.setTitile(input.getTitile());
        command.setMsgContent(input.getMsgContent()); command.setStartTime(input.getStartTime());
        command.setEndTime(input.getEndTime()); command.setPriority(input.getPriority());
        command.setMsgCategory(input.getMsgCategory()); command.setMsgType(input.getMsgType());
        command.setUserIds(input.getUserIds()); command.setMsgAbstract(input.getMsgAbstract());
        return command;
    }
}
