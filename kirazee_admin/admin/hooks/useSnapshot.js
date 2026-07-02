import { useState, useEffect } from 'react';
import { dashboardSnapshotService } from '../services/dashboardSnapshotService';

export const useSnapshot = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const refreshStatus = async () => {
    setLoading(true);
    setError('');
    
    try {
      const result = await dashboardSnapshotService.getSnapshotStatus();
      if (result.success) {
        setStatus(result.data);
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError('Failed to load status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const calculateSnapshot = async () => {
    setLoading(true);
    try {
      const result = await dashboardSnapshotService.calculateSnapshot();
      if (result.success) {
        await refreshStatus();
        return result;
      }
      throw new Error(result.message);
    } finally {
      setLoading(false);
    }
  };

  return {
    status,
    loading,
    error,
    refreshStatus,
    calculateSnapshot
  };
};
