package org.jeecg.accountrecovery;

import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.service.*;
import org.junit.Before;
import org.junit.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

public class AccountRecoveryServiceTest {
    private ISysUserService users;
    private PasswordResetCodeStore codes;
    private PasswordResetSmsSender sender;
    private PasswordResetService service;
    private SysUser user;

    @Before public void setup() {
        TableInfoHelper.initTableInfo(new MapperBuilderAssistant(new MybatisConfiguration(), "account-recovery-test"), SysUser.class);
        users = mock(ISysUserService.class); codes = mock(PasswordResetCodeStore.class);
        sender = mock(PasswordResetSmsSender.class); service = new PasswordResetService(users, codes, sender);
        user = new SysUser().setId("synthetic-id").setUsername("synthetic-user").setPhone("13900000001").setStatus(1).setDelFlag(0);
        when(users.getOne(any())).thenReturn(user);
        when(codes.consume(user.getId(), user.getPhone(), "123456")).thenReturn(true);
        when(users.update(any(SysUser.class), any())).thenReturn(true);
    }
    private JSONObject request() {
        JSONObject r = new JSONObject(); r.put("username", user.getUsername()); r.put("phone", user.getPhone());
        r.put("smscode", "123456"); r.put("password", "Synthetic8!"); return r;
    }
    private void failed(Result<?> r, int code) { assertFalse(r.isSuccess()); assertEquals(Integer.valueOf(code), r.getCode()); assertNull(r.getResult()); }
    @Test public void validPasswordRequiresLetterDigitSpecialAndBoundedAscii() {
        assertTrue(PasswordResetService.validPassword("abcd123!"));
        assertTrue(PasswordResetService.validPassword("ABCD123!"));
        assertFalse(PasswordResetService.validPassword(null));
        assertFalse(PasswordResetService.validPassword("Ab1!"));
        assertFalse(PasswordResetService.validPassword("12345678!"));
        assertFalse(PasswordResetService.validPassword("abcdefgh!"));
        assertFalse(PasswordResetService.validPassword("abcd1234"));
        assertFalse(PasswordResetService.validPassword(" Abcd12!"));
        assertFalse(PasswordResetService.validPassword("Abcd12!中文"));
        assertFalse(PasswordResetService.validPassword("Abcd12!\n"));
        assertFalse(PasswordResetService.validPassword(new String(new char[65]).replace('\0', 'a') + "1!"));
    }
    @Test public void invalidPasswordNeverConsumesCode() {
        JSONObject r = request(); r.put("password", "Abcd123!中文"); failed(service.reset(r), 400);
        verifyZeroInteractions(users, codes, sender);
    }
    @Test public void nonStringPasswordIsRejected() {
        JSONObject r = request(); r.put("password", 123456789); failed(service.reset(r), 400); verifyZeroInteractions(codes);
    }
    @Test public void nonStringAndNullRequestAreRejected() {
        JSONObject r = request(); r.put("smscode", new JSONObject()); failed(service.verify(r), 400);
        failed(service.verify(null), 400); failed(service.reset(null), 400); verifyZeroInteractions(users, codes);
    }
    @Test public void invalidPhoneNeverQueriesOrConsumes() {
        JSONObject r = request(); r.put("phone", "139****0001"); failed(service.reset(r), 400); verifyZeroInteractions(users, codes);
    }
    @Test public void missingUsernameNeverQueriesOrConsumes() {
        JSONObject r = request(); r.remove("username"); failed(service.reset(r), 400); verifyZeroInteractions(users, codes);
    }
    @Test public void noBoundAccountNeverConsumes() { when(users.getOne(any())).thenReturn(null); failed(service.reset(request()), 400); verifyZeroInteractions(codes); }
    @Test public void frozenAccountNeverConsumes() { user.setStatus(2); failed(service.reset(request()), 400); verifyZeroInteractions(codes); }
    @Test public void deletedAccountNeverConsumes() { user.setDelFlag(1); failed(service.reset(request()), 400); verifyZeroInteractions(codes); }
    @Test public void invalidAccountStateNeverConsumes() { user.setStatus(null); failed(service.reset(request()), 400); verifyZeroInteractions(codes); }
    @Test public void verificationIsReadOnlyAndReturnsNoCode() {
        when(codes.matches(user.getId(), user.getPhone(), "123456")).thenReturn(true);
        Result<?> r = service.verify(request()); assertTrue(r.isSuccess()); assertNull(r.getResult());
        verify(codes).matches(user.getId(), user.getPhone(), "123456"); verifyNoMoreInteractions(codes); verify(users, never()).update(any(), any());
    }
    @Test public void wrongVerificationFails() { failed(service.verify(request()), 400); verify(users, never()).update(any(), any()); }
    @Test public void expiredConsumedOrWrongCodeNeverUpdates() {
        when(codes.consume(user.getId(), user.getPhone(), "123456")).thenReturn(false);
        failed(service.reset(request()), 400); verify(users, never()).update(any(), any()); verify(codes, never()).clearUserCaches(any(), any());
    }
    @Test public void redisConsumeFailureNeverUpdates() {
        when(codes.consume(user.getId(), user.getPhone(), "123456")).thenThrow(new IllegalStateException());
        failed(service.reset(request()), 500); verify(users, never()).update(any(), any());
    }
    @Test public void resetConsumesThenWritesOnlyPasswordAndSaltThenClearsCaches() {
        Result<?> result = service.reset(request()); assertTrue(result.isSuccess()); assertNull(result.getResult());
        ArgumentCaptor<SysUser> updated = ArgumentCaptor.forClass(SysUser.class);
        ArgumentCaptor<LambdaUpdateWrapper> conditions = ArgumentCaptor.forClass(LambdaUpdateWrapper.class);
        InOrder order = inOrder(codes, users); order.verify(users).getOne(any());
        order.verify(codes).consume(user.getId(), user.getPhone(), "123456"); order.verify(users).update(updated.capture(), conditions.capture());
        order.verify(codes).clearUserCaches(user.getId(), user.getUsername());
        assertNotNull(updated.getValue().getPassword()); assertNotEquals("Synthetic8!", updated.getValue().getPassword());
        assertEquals(8, updated.getValue().getSalt().length()); assertNull(updated.getValue().getId());
        assertNull(updated.getValue().getUsername()); assertNull(updated.getValue().getPhone()); assertNull(updated.getValue().getStatus());
        String sql = conditions.getValue().getSqlSegment();
        for (String column : new String[]{"id", "username", "phone", "status", "del_flag"}) assertTrue(sql.contains(column + " ="));
        assertTrue(conditions.getValue().getParamNameValuePairs().containsValue(user.getId()));
        assertTrue(conditions.getValue().getParamNameValuePairs().containsValue(user.getUsername()));
        assertTrue(conditions.getValue().getParamNameValuePairs().containsValue(user.getPhone()));
        assertTrue(conditions.getValue().getParamNameValuePairs().containsValue(1));
        assertTrue(conditions.getValue().getParamNameValuePairs().containsValue(0));
    }
    @Test public void updateFalseReportsConsumedFailure() {
        when(users.update(any(SysUser.class), any())).thenReturn(false); Result<?> r = service.reset(request()); failed(r, 500);
        assertTrue(r.getMessage().contains("验证码已使用")); assertEquals("code_consumed", ((PasswordResetService.RecoveryResult) r).getRecoveryState()); verify(codes, never()).clearUserCaches(any(), any());
    }
    @Test public void updateExceptionReportsUncertainConsumedFailure() {
        when(users.update(any(SysUser.class), any())).thenThrow(new IllegalStateException()); Result<?> r = service.reset(request()); failed(r, 500);
        assertTrue(r.getMessage().contains("结果不确定")); assertTrue(r.getMessage().contains("验证码已使用")); assertEquals("reset_unknown", ((PasswordResetService.RecoveryResult) r).getRecoveryState());
    }
    @Test public void cacheExceptionReportsPasswordChangedWithoutSuccess() {
        doThrow(new IllegalStateException()).when(codes).clearUserCaches(any(), any()); Result<?> r = service.reset(request()); failed(r, 500);
        assertTrue(r.getMessage().startsWith("密码已重置")); assertEquals("reset_committed", ((PasswordResetService.RecoveryResult) r).getRecoveryState());
    }
    @Test public void sendingChecksBoundAccountBeforeAnySms() throws Exception {
        when(users.getOne(any())).thenReturn(null); failed(service.sendCode(user.getUsername(), user.getPhone()), 400); verifyZeroInteractions(codes, sender);
    }
    @Test public void sendReservationPreventsDuplicateSms() throws Exception {
        Result<?> r = service.sendCode(user.getUsername(), user.getPhone()); failed(r, 400); assertEquals("code_active", ((PasswordResetService.RecoveryResult) r).getRecoveryState()); verifyZeroInteractions(sender); verify(codes, never()).publish(any(), any(), any(), any());
    }
    @Test public void sendingPublishesOnlyAfterSuccessfulSmsAndNeverEchoes() throws Exception {
        when(codes.reserve(any(), any(), any())).thenReturn(true); when(sender.send(any(), any())).thenReturn(true);
        when(codes.publish(any(), any(), any(), any())).thenReturn(true); Result<?> r = service.sendCode(user.getUsername(), user.getPhone());
        assertTrue(r.isSuccess()); assertNull(r.getResult()); InOrder order = inOrder(sender, codes);
        order.verify(codes).reserve(eq(user.getId()), eq(user.getPhone()), startsWith("pending:"));
        order.verify(sender).send(eq(user.getPhone()), matches("[0-9]{6}"));
        order.verify(codes).publish(eq(user.getId()), eq(user.getPhone()), startsWith("pending:"), matches("[0-9]{6}"));
    }
    @Test public void smsFailureDiscardsReservationAndDoesNotPublish() throws Exception {
        when(codes.reserve(any(), any(), any())).thenReturn(true); failed(service.sendCode(user.getUsername(), user.getPhone()), 500);
        verify(codes).consume(eq(user.getId()), eq(user.getPhone()), startsWith("pending:")); verify(codes, never()).publish(any(), any(), any(), any());
    }
    @Test public void smsExceptionIsFixedFailureWithoutSensitiveEcho() throws Exception {
        when(codes.reserve(any(), any(), any())).thenReturn(true); when(sender.send(any(), any())).thenThrow(new RuntimeException("private credential"));
        Result<?> r = service.sendCode(user.getUsername(), user.getPhone()); failed(r, 500); assertFalse(r.getMessage().contains("private"));
    }
    @Test public void smsSuccessPublishFailureIsExplicitFailure() throws Exception {
        when(codes.reserve(any(), any(), any())).thenReturn(true); when(sender.send(any(), any())).thenReturn(true);
        Result<?> r = service.sendCode(user.getUsername(), user.getPhone()); failed(r, 500); assertTrue(r.getMessage().contains("短信已发送"));
    }
}
