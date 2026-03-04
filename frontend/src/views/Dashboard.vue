<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<template>
  <div class="max-w-7xl mx-auto">
    <header class="mb-12 flex items-end justify-between border-b border-border pb-6">
      <div>
        <h1 class="text-4xl font-bold text-primary mb-2 tracking-tight">
          {{ t('dashboard.title').toUpperCase() }}
        </h1>
        <p class="text-text-secondary font-mono text-sm">
          {{ t('dashboard.subtitle') }} // SYSTEM_READY
        </p>
      </div>
      <div class="text-right hidden sm:block">
        <div class="text-xs text-text-secondary mb-1">CURRENT_SESSION</div>
        <div class="font-mono text-primary">ID: 8X-9921-AZ</div>
      </div>
    </header>
    
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
      <!-- Quick Actions Module -->
      <div class="terminal-card lg:col-span-2">
        <div class="flex items-center justify-between mb-6">
          <h3 class="text-sm font-bold text-text-secondary uppercase tracking-widest flex items-center">
            <span class="w-2 h-2 bg-primary mr-2 animate-pulse"></span>
            OPERATION_MODULES
          </h3>
          <span class="text-[10px] border border-border px-1 text-text-secondary">SEC_LEVEL_1</span>
        </div>
        
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <router-link 
            to="/ingest" 
            class="group border border-border bg-black/20 p-6 hover:border-primary hover:bg-primary/5 transition-all duration-0 relative overflow-hidden"
          >
            <div class="absolute top-0 right-0 p-2 opacity-20 text-4xl group-hover:opacity-40 transition-opacity">📥</div>
            <div class="relative z-10">
              <div class="text-xs text-primary mb-2 opacity-70">CMD_01</div>
              <div class="font-bold text-xl mb-2 group-hover:text-primary group-hover:translate-x-1 transition-transform">
                {{ t('dashboard.ingestContent').toUpperCase() }}
              </div>
              <div class="h-1 w-8 bg-border group-hover:bg-primary transition-colors"></div>
            </div>
          </router-link>

          <router-link 
            to="/authors" 
            class="group border border-border bg-black/20 p-6 hover:border-tertiary hover:bg-tertiary/5 transition-all duration-0 relative overflow-hidden"
          >
            <div class="absolute top-0 right-0 p-2 opacity-20 text-4xl group-hover:opacity-40 transition-opacity">◈</div>
            <div class="relative z-10">
              <div class="text-xs text-tertiary mb-2 opacity-70">CMD_02</div>
              <div class="font-bold text-xl mb-2 group-hover:text-tertiary group-hover:translate-x-1 transition-transform">
                {{ t('dashboard.exploreAuthors').toUpperCase() }}
              </div>
              <div class="h-1 w-8 bg-border group-hover:bg-tertiary transition-colors"></div>
            </div>
          </router-link>
          
          <router-link 
            to="/chat" 
            class="group border border-border bg-black/20 p-6 hover:border-secondary hover:bg-secondary/5 transition-all duration-0 relative overflow-hidden"
          >
            <div class="absolute top-0 right-0 p-2 opacity-20 text-4xl group-hover:opacity-40 transition-opacity">💬</div>
            <div class="relative z-10">
              <div class="text-xs text-secondary mb-2 opacity-70">CMD_03</div>
              <div class="font-bold text-xl mb-2 group-hover:text-secondary group-hover:translate-x-1 transition-transform">
                CHAT_INTERFACE
              </div>
              <div class="h-1 w-8 bg-border group-hover:bg-secondary transition-colors"></div>
            </div>
          </router-link>
          
           <router-link 
            to="/llm-calls" 
            class="group border border-border bg-black/20 p-6 hover:border-white hover:bg-white/5 transition-all duration-0 relative overflow-hidden"
          >
            <div class="absolute top-0 right-0 p-2 opacity-20 text-4xl group-hover:opacity-40 transition-opacity">⚡</div>
            <div class="relative z-10">
              <div class="text-xs text-white mb-2 opacity-70">CMD_04</div>
              <div class="font-bold text-xl mb-2 group-hover:text-white group-hover:translate-x-1 transition-transform">
                SYSTEM_LOGS
              </div>
              <div class="h-1 w-8 bg-border group-hover:bg-white transition-colors"></div>
            </div>
          </router-link>
        </div>
      </div>

      <!-- System Stats Module -->
      <div class="space-y-6">
        <div class="terminal-card h-full">
           <div class="flex items-center justify-between mb-6">
            <h3 class="text-sm font-bold text-text-secondary uppercase tracking-widest flex items-center">
              <span class="w-2 h-2 bg-secondary mr-2"></span>
              SYSTEM_METRICS
            </h3>
             <span class="text-[10px] animate-pulse text-secondary">LIVE</span>
          </div>
          
          <div class="space-y-6 font-mono">
            <div class="relative">
              <div class="flex justify-between text-xs text-text-secondary mb-1">
                <span>VECTOR_INDEX_LOAD</span>
                <span>84%</span>
              </div>
              <div class="w-full bg-border h-2">
                <div class="bg-primary h-2 w-[84%]"></div>
              </div>
            </div>
            
            <div class="grid grid-cols-2 gap-4 pt-4 border-t border-border">
              <div>
                <div class="text-[10px] text-text-secondary uppercase">Active_Nodes</div>
                <div class="text-2xl font-bold text-white">12</div>
              </div>
              <div>
                <div class="text-[10px] text-text-secondary uppercase">Query_Latency</div>
                <div class="text-2xl font-bold text-tertiary">42ms</div>
              </div>
              <div>
                <div class="text-[10px] text-text-secondary uppercase">Ingest_Rate</div>
                <div class="text-2xl font-bold text-secondary">2.4/s</div>
              </div>
              <div>
                <div class="text-[10px] text-text-secondary uppercase">Total_Tokens</div>
                <div class="text-2xl font-bold text-primary">1.2M</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
