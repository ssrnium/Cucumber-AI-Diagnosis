package com.portfolio.cucumber.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityUtils {

    private SecurityUtils() {
    }

    public static LoginUser current() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null && authentication.getPrincipal() instanceof LoginUser loginUser) {
            return loginUser;
        }
        return null;
    }

    public static Long currentUserId() {
        LoginUser loginUser = current();
        return loginUser == null ? null : loginUser.getUserId();
    }

    public static boolean hasAuthority(String authority) {
        LoginUser loginUser = current();
        if (loginUser == null) {
            return false;
        }
        return loginUser.getAuthorities().stream()
                .anyMatch(a -> authority.equals(a.getAuthority()));
    }
}
