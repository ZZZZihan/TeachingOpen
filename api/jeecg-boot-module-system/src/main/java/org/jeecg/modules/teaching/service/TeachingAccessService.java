package org.jeecg.modules.teaching.service;

import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.system.vo.LoginUser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/** Resource checks for endpoints shared by learning and management pages. */
@Service
public class TeachingAccessService {
    @Autowired private ITeachingCourseDeptService courseDeptService;

    public LoginUser currentUser() {
        return (LoginUser) SecurityUtils.getSubject().getPrincipal();
    }

    public boolean isAdministrator() {
        return SecurityUtils.getSubject().hasRole("admin") || SecurityUtils.getSubject().hasRole("dev");
    }

    public void requireCourse(String courseId) {
        LoginUser user = currentUser();
        if (user == null || (!isAdministrator() && !courseDeptService.checkCoursePermission(courseId, user.getId()))) {
            throw new UnauthorizedException("无课程权限");
        }
    }
}
