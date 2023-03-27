%global desc %{expand:
Python bindings for the AWS Common Runtime}


Name:           python-awscrt
Version:        0.16.16
Release:        1%{?dist}

Summary:        Python bindings for the AWS Common Runtime
# All files are licensed under Apache-2.0, except:
# - crt/aws-c-common/include/aws/common/external/cJSON.h is MIT
# - crt/aws-c-common/source/external/cJSON.c is MIT
# - crt/s2n/pq-crypto/kyber_r3/KeccakP-brg_endian_avx2.h is BSD-3-Clause
License:        Apache-2.0 AND MIT AND BSD-3-Clause
URL:            https://github.com/awslabs/aws-crt-python

Source0:        %{pypi_source awscrt}

# one test requires internet connection, skip it
Patch0:         skip-test-requiring-network.patch

BuildRequires:  python%{python3_pkgversion}-devel

BuildRequires:  gcc
BuildRequires:  gcc-c++
BuildRequires:  cmake
BuildRequires:  openssl-devel

BuildRequires:  python%{python3_pkgversion}-websockets

# https://bugzilla.redhat.com/show_bug.cgi?id=2180988
ExcludeArch:    s390x


%description
%{desc}


%package -n python%{python3_pkgversion}-awscrt
Summary:        %{summary}


%description -n python%{python3_pkgversion}-awscrt
%{desc}


%prep
%autosetup -p1 -n awscrt-%{version}


%generate_buildrequires
%pyproject_buildrequires


%build
%ifarch %{ix86}
# disable SSE2 instructions to prevent a crash in aws-c-common thread handling
# probably caused by a compiler bug
export CFLAGS="%{optflags} -mno-sse2"
%endif
export AWS_CRT_BUILD_USE_SYSTEM_LIBCRYPTO=1
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files _awscrt awscrt


%check
PYTHONPATH="%{buildroot}%{python3_sitearch}:%{buildroot}%{python3_sitelib}" %{python3} -m unittest


%files -n python%{python3_pkgversion}-awscrt -f %{pyproject_files}
%doc README.md


%changelog
%autochangelog
