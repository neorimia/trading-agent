import { inject } from '@angular/core';
import { CanActivateFn } from '@angular/router';

import { AgentStateService } from './agent-state.service';

/** Viewing is always allowed. Mutations are blocked in components when observer or halted. */
export const permissionGuard: CanActivateFn = () => {
  inject(AgentStateService);
  return true;
};

export const liveApproveBlocked = (): boolean => {
  if (typeof window === 'undefined') {
    return true;
  }
  return window.innerWidth < 768;
};
