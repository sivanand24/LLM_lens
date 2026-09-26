import { Routes } from '@angular/router';

import { DashboardPageComponent } from './dashboard/dashboard-page.component';

export const routes: Routes = [
  { path: '', component: DashboardPageComponent },
  { path: '**', redirectTo: '' },
];
