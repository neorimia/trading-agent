import { Routes } from '@angular/router';

import { permissionGuard } from './core/permission.guard';
import { AgentPage } from './features/agent.page';
import { AssetPage } from './features/asset.page';
import { DashboardPage } from './features/dashboard.page';
import { MarketPage } from './features/market.page';
import { OrdersPage } from './features/orders.page';
import { ResearchPage } from './features/research.page';
import { RiskPage } from './features/risk.page';
import { SettingsPage } from './features/settings.page';
import { StrategiesPage } from './features/strategies.page';

export const routes: Routes = [
  { path: '', component: DashboardPage, canActivate: [permissionGuard] },
  { path: 'market', component: MarketPage, canActivate: [permissionGuard] },
  { path: 'market/:symbol', component: AssetPage, canActivate: [permissionGuard] },
  { path: 'strategies', component: StrategiesPage, canActivate: [permissionGuard] },
  { path: 'orders', component: OrdersPage, canActivate: [permissionGuard] },
  { path: 'risk', component: RiskPage, canActivate: [permissionGuard] },
  { path: 'research', component: ResearchPage, canActivate: [permissionGuard] },
  { path: 'agent', component: AgentPage, canActivate: [permissionGuard] },
  { path: 'settings', component: SettingsPage, canActivate: [permissionGuard] },
];
