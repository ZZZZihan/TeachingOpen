package org.jeecg.modules.system.model;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.Data;
import org.jeecg.common.aspect.annotation.Dict;
import org.jeecg.modules.system.entity.SysUser;
import java.util.Date;

/** Deliberate read contract. No credential, third-party identity or internal audit fields. */
@Data
@JsonInclude(JsonInclude.Include.NON_NULL)
public class UserProfileView {
    private String id;
    private String username;
    private String realname;
    private String avatar;
    private String orgCode;
    private String orgCodeTxt;
    private String roleTxt;
    private String workNo;
    private String post;
    private String school;
    @Dict(dicCode="sex") private Integer sex;
    @JsonFormat(timezone="GMT+8",pattern="yyyy-MM-dd") private Date birthday;
    private String email;
    private String phone;
    private String telephone;
    @Dict(dicCode="user_status") private Integer status;
    private Integer delFlag;
    private Integer userIdentity;
    @Dict(dictTable="sys_depart",dicText="depart_name",dicCode="id") private String departIds;
    @JsonFormat(timezone="GMT+8",pattern="yyyy-MM-dd HH:mm:ss") private Date createTime;
    @JsonFormat(timezone="GMT+8",pattern="yyyy-MM-dd HH:mm:ss") private Date updateTime;

    public static UserProfileView from(SysUser user, boolean own, boolean administrator) {
        UserProfileView view=new UserProfileView();
        view.id=user.getId(); view.username=user.getUsername(); view.realname=user.getRealname(); view.avatar=user.getAvatar();
        view.orgCodeTxt=user.getOrgCodeTxt(); view.roleTxt=user.getRoleTxt();
        if (own || administrator) {
            view.sex=user.getSex(); view.birthday=user.getBirthday(); view.email=user.getEmail();
            view.phone=user.getPhone(); view.telephone=user.getTelephone(); view.school=user.getSchool();
            view.workNo=user.getWorkNo(); view.post=user.getPost(); view.orgCode=user.getOrgCode();
        }
        if (administrator) {
            view.status=user.getStatus(); view.delFlag=user.getDelFlag(); view.userIdentity=user.getUserIdentity();
            view.departIds=user.getDepartIds(); view.createTime=user.getCreateTime(); view.updateTime=user.getUpdateTime();
        }
        return view;
    }
}
